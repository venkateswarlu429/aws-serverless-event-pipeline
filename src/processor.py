"""Processor handler: SQS -> DynamoDB, idempotently.

Design rules that make this safe under SQS's at-least-once delivery:

* **Idempotent writes** — the event ID is the DynamoDB partition key and the
  write is conditional on ``attribute_not_exists``. A redelivered message
  hits the condition, is recognised as a duplicate, and is treated as a
  success (deleted from the queue), never an overwrite.
* **Partial batch responses** — the function only reports the message IDs
  that genuinely failed (``ReportBatchItemFailures``). Lambda deletes the
  rest, so one poison message can't force the whole batch to retry.
* **Poison messages** — a message that keeps failing is retried until the
  queue's ``maxReceiveCount`` trips and SQS moves it to the DLQ, where an
  alarm fires. Nothing is silently dropped.
"""

import json
import logging
import os
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from lib.clients import get_client
from lib.logging_setup import configure_logger, log, set_correlation_id

logger = configure_logger("processor")


def _process_record(record: dict) -> None:
    """Process one SQS record. Raises on any failure the batch should retry."""
    envelope = json.loads(record["body"])  # ValueError -> malformed message
    event_id = envelope["event_id"]  # KeyError -> malformed message
    set_correlation_id(envelope.get("correlation_id", "-"))

    item = {
        "event_id": event_id,
        "correlation_id": envelope.get("correlation_id", "-"),
        "type": envelope.get("type", "unknown"),
        "source": envelope.get("source", "unknown"),
        "data": envelope.get("data", {}),
        "received_at": envelope.get("received_at", ""),
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }

    dynamodb = get_client("dynamodb")
    try:
        dynamodb.put_item(
            TableName=os.environ["TABLE_NAME"],
            Item=_to_dynamodb(item),
            ConditionExpression="attribute_not_exists(event_id)",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            # Duplicate delivery of an already-processed event. This is the
            # expected, healthy outcome of at-least-once delivery — log it
            # and return normally so the message is deleted, not retried.
            log(logger, logging.INFO, "Duplicate event ignored", event_id=event_id)
            return
        raise

    log(logger, logging.INFO, "Event processed", event_id=event_id, event_type=item["type"])


def _to_dynamodb(item: dict) -> dict:
    """Convert the plain dict to DynamoDB's typed attribute format."""
    def convert(value):
        if isinstance(value, str):
            return {"S": value}
        if isinstance(value, bool):
            return {"BOOL": value}
        if isinstance(value, (int, float)):
            return {"N": str(value)}
        if isinstance(value, dict):
            return {"M": {k: convert(v) for k, v in value.items()}}
        if isinstance(value, list):
            return {"L": [convert(v) for v in value]}
        if value is None:
            return {"NULL": True}
        return {"S": str(value)}

    return {k: convert(v) for k, v in item.items()}


def handler(event, context=None):
    failures = []
    for record in event.get("Records", []):
        try:
            _process_record(record)
        except Exception:
            # Deliberately broad: any per-record failure (bad JSON, missing
            # key, DynamoDB throttling, ...) marks just this message for
            # retry/DLQ while the rest of the batch succeeds.
            logger.exception(
                "Failed to process message",
                extra={"fields": {"message_id": record.get("messageId")}},
            )
            failures.append({"itemIdentifier": record["messageId"]})
    # Shape required by Lambda's ReportBatchItemFailures contract.
    return {"batchItemFailures": failures}
