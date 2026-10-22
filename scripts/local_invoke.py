#!/usr/bin/env python3
"""Run both handlers locally against the fixtures in events/ — no AWS needed.

Uses moto to stand in for SQS and DynamoDB in-process, then:
  1. feeds events/api_event_valid.json to the ingest handler,
  2. takes the message the handler actually enqueued, wraps it in an SQS
     event envelope, and feeds it to the processor handler,
  3. reads the item back out of DynamoDB to prove the write landed.

Usage:
    pip install -r tests/requirements.txt
    python scripts/local_invoke.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault("AWS_ACCESS_KEY_ID", "local")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "local")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

import boto3  # noqa: E402
from moto import mock_aws  # noqa: E402

EVENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "events")
TABLE_NAME = "events-local"


def load(name: str) -> dict:
    with open(os.path.join(EVENTS_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    with mock_aws():
        sqs = boto3.client("sqs")
        queue_url = sqs.create_queue(QueueName="events-local")["QueueUrl"]
        dynamodb = boto3.client("dynamodb")
        dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "event_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "event_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        os.environ["QUEUE_URL"] = queue_url
        os.environ["TABLE_NAME"] = TABLE_NAME

        import ingest
        import processor

        print("== ingest: valid API Gateway event ==")
        response = ingest.handler(load("api_event_valid.json"))
        print(json.dumps(response, indent=2))
        assert response["statusCode"] == 202

        print("\n== ingest: invalid event type is rejected ==")
        response = ingest.handler(load("api_event_invalid.json"))
        print(json.dumps(response, indent=2))
        assert response["statusCode"] == 400

        # Pull the real message off the queue and hand it to the processor
        # exactly the way Lambda's SQS integration would.
        message = sqs.receive_message(
            QueueUrl=queue_url,
            AttributeNames=["All"],
            MessageAttributeNames=["All"],
        )["Messages"][0]
        sqs_event = {
            "Records": [
                {
                    "messageId": message["MessageId"],
                    "receiptHandle": message["ReceiptHandle"],
                    "body": message["Body"],
                    "attributes": message.get("Attributes", {}),
                    "messageAttributes": message.get("MessageAttributes", {}),
                    "eventSource": "aws:sqs",
                    "eventSourceARN": "arn:aws:sqs:us-east-1:123456789012:events-local",
                    "awsRegion": "us-east-1",
                }
            ]
        }

        print("\n== processor: consume the queued message ==")
        result = processor.handler(sqs_event)
        print("batchItemFailures:", result["batchItemFailures"])
        assert result == {"batchItemFailures": []}

        print("\n== processor: redeliver the same message (idempotency) ==")
        result = processor.handler(sqs_event)
        print("batchItemFailures:", result["batchItemFailures"])
        assert result == {"batchItemFailures": []}

        envelope = json.loads(message["Body"])
        item = dynamodb.get_item(
            TableName=TABLE_NAME, Key={"event_id": {"S": envelope["event_id"]}}
        )["Item"]
        print("\n== DynamoDB item ==")
        print(json.dumps(item, indent=2, default=str))
        print("\nLocal invoke OK: ingest -> SQS -> processor -> DynamoDB.")


if __name__ == "__main__":
    main()
