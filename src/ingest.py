"""Ingest handler: API Gateway (HTTP API) -> validation -> SQS.

Synchronous and deliberately thin. It validates the request, stamps it with
an event ID and correlation ID, enqueues it, and returns 202 immediately.
All real work happens asynchronously in the processor, so a slow downstream
can never turn into API latency or a client-visible timeout.
"""

import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from lib.clients import get_client
from lib.logging_setup import configure_logger, log, set_correlation_id
from lib.responses import error_response, json_response
from lib.validation import ValidationError, validate_event_payload

logger = configure_logger("ingest")


def _extract_correlation_id(event: dict) -> str:
    """Reuse the caller's correlation ID if supplied, else mint one."""
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    return headers.get("x-correlation-id") or uuid.uuid4().hex


def _decode_body(event: dict):
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    return json.loads(body) if body else None


def handler(event, context=None):
    correlation_id = _extract_correlation_id(event)
    set_correlation_id(correlation_id)

    try:
        payload = _decode_body(event)
    except (ValueError, UnicodeDecodeError):
        log(logger, logging.WARNING, "Rejected malformed JSON body")
        return error_response(400, "Request body must be valid JSON.", correlation_id)

    try:
        validated = validate_event_payload(payload)
    except ValidationError as exc:
        log(logger, logging.WARNING, "Rejected invalid event", reason=str(exc))
        return error_response(400, str(exc), correlation_id)

    event_id = uuid.uuid4().hex
    envelope = {
        "event_id": event_id,
        "correlation_id": correlation_id,
        "type": validated["type"],
        "source": validated["source"],
        "data": validated["data"],
        "received_at": datetime.now(timezone.utc).isoformat(),
    }

    sqs = get_client("sqs")
    sqs.send_message(
        QueueUrl=os.environ["QUEUE_URL"],
        MessageBody=json.dumps(envelope),
        # Attributes mirror the body fields so messages can be traced in the
        # SQS console / CloudWatch without parsing the body.
        MessageAttributes={
            "event_id": {"DataType": "String", "StringValue": event_id},
            "correlation_id": {"DataType": "String", "StringValue": correlation_id},
            "event_type": {"DataType": "String", "StringValue": validated["type"]},
        },
    )
    log(
        logger,
        logging.INFO,
        "Event accepted",
        event_id=event_id,
        event_type=validated["type"],
    )
    return json_response(
        202,
        {"status": "accepted", "event_id": event_id, "correlation_id": correlation_id},
    )
