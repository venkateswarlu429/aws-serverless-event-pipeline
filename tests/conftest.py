import json
import os
import sys

# Make src/ importable and give boto3 fake credentials so nothing can ever
# accidentally reach real AWS from a test run.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_SESSION_TOKEN", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("LOG_LEVEL", "INFO")

import boto3  # noqa: E402
import pytest  # noqa: E402
from moto import mock_aws  # noqa: E402

from lib.clients import reset_clients  # noqa: E402

EVENTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "events"))
TABLE_NAME = "test-events-table"


def load_fixture(name: str) -> dict:
    with open(os.path.join(EVENTS_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture()
def aws_env():
    """A moto-backed SQS queue + DynamoDB table, wired up via env vars."""
    with mock_aws():
        reset_clients()
        sqs = boto3.client("sqs")
        queue_url = sqs.create_queue(QueueName="test-events")["QueueUrl"]

        dynamodb = boto3.client("dynamodb")
        dynamodb.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "event_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "event_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )

        os.environ["QUEUE_URL"] = queue_url
        os.environ["TABLE_NAME"] = TABLE_NAME
        yield {"queue_url": queue_url, "table_name": TABLE_NAME}
        reset_clients()


def receive_one(queue_url: str) -> dict:
    sqs = boto3.client("sqs")
    resp = sqs.receive_message(
        QueueUrl=queue_url, MessageAttributeNames=["All"], WaitTimeSeconds=0
    )
    messages = resp.get("Messages", [])
    assert len(messages) == 1, f"expected exactly 1 queued message, got {len(messages)}"
    return messages[0]


def queue_depth(queue_url: str) -> int:
    sqs = boto3.client("sqs")
    resp = sqs.receive_message(QueueUrl=queue_url, WaitTimeSeconds=0)
    return len(resp.get("Messages", []))


def get_item(table_name: str, event_id: str) -> dict | None:
    dynamodb = boto3.client("dynamodb")
    resp = dynamodb.get_item(TableName=table_name, Key={"event_id": {"S": event_id}})
    return resp.get("Item")
