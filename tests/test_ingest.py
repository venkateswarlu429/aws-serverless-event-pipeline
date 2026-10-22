"""Ingest handler: validation, 202 contract, SQS envelope, correlation IDs."""

import json

import ingest
from conftest import load_fixture, queue_depth, receive_one


def test_ingest_accepts_valid_event(aws_env):
    response = ingest.handler(load_fixture("api_event_valid.json"))

    assert response["statusCode"] == 202
    body = json.loads(response["body"])
    assert body["status"] == "accepted"
    assert body["event_id"]
    # The caller-supplied correlation ID from the fixture header is honoured.
    assert body["correlation_id"] == "corr-fixture-0001"

    message = receive_one(aws_env["queue_url"])
    envelope = json.loads(message["Body"])
    assert envelope["event_id"] == body["event_id"]
    assert envelope["correlation_id"] == "corr-fixture-0001"
    assert envelope["type"] == "order.created"
    assert envelope["data"]["order_id"] == "ord-1001"
    # Message attributes mirror the envelope for console-level tracing.
    assert message["MessageAttributes"]["event_id"]["StringValue"] == body["event_id"]
    assert (
        message["MessageAttributes"]["correlation_id"]["StringValue"]
        == "corr-fixture-0001"
    )


def test_ingest_rejects_unsupported_event_type(aws_env):
    response = ingest.handler(load_fixture("api_event_invalid.json"))

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert "Unsupported event type" in body["error"]
    assert queue_depth(aws_env["queue_url"]) == 0  # nothing enqueued


def test_ingest_rejects_malformed_json(aws_env):
    event = load_fixture("api_event_valid.json")
    event["body"] = "this is not json {{{"

    response = ingest.handler(event)

    assert response["statusCode"] == 400
    assert queue_depth(aws_env["queue_url"]) == 0


def test_ingest_rejects_missing_data_field(aws_env):
    event = load_fixture("api_event_valid.json")
    event["body"] = json.dumps({"type": "order.created"})  # no 'data'

    response = ingest.handler(event)

    assert response["statusCode"] == 400
    assert "'data'" in json.loads(response["body"])["error"]
    assert queue_depth(aws_env["queue_url"]) == 0


def test_ingest_generates_correlation_id_when_absent(aws_env):
    event = load_fixture("api_event_valid.json")
    event["headers"] = {"content-type": "application/json"}  # no correlation header

    response = ingest.handler(event)

    assert response["statusCode"] == 202
    body = json.loads(response["body"])
    assert body["correlation_id"]  # generated, non-empty
    message = receive_one(aws_env["queue_url"])
    assert json.loads(message["Body"])["correlation_id"] == body["correlation_id"]
