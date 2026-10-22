"""Processor handler: happy path, idempotency, partial batch failures."""

import json

import processor
from conftest import get_item, load_fixture


def test_processor_happy_path(aws_env):
    result = processor.handler(load_fixture("sqs_event.json"))

    assert result == {"batchItemFailures": []}
    item = get_item(aws_env["table_name"], "evt-fixture-0001")
    assert item is not None
    assert item["type"]["S"] == "order.created"
    assert item["correlation_id"]["S"] == "corr-fixture-0001"
    assert item["data"]["M"]["order_id"]["S"] == "ord-1001"
    assert item["data"]["M"]["amount"]["N"] == "42.5"
    assert item["processed_at"]["S"]  # stamped at write time


def test_processor_duplicate_delivery_is_idempotent(aws_env):
    event = load_fixture("sqs_event.json")
    assert processor.handler(event) == {"batchItemFailures": []}

    # Same event_id redelivered (at-least-once), this time with *different*
    # payload data — the conditional write must refuse to overwrite.
    duplicate = json.loads(json.dumps(event))
    envelope = json.loads(duplicate["Records"][0]["body"])
    envelope["data"]["order_id"] = "ord-SHOULD-NOT-WIN"
    duplicate["Records"][0]["body"] = json.dumps(envelope)

    result = processor.handler(duplicate)
    # A duplicate is a success, not a failure: no batch-item failure reported.
    assert result == {"batchItemFailures": []}

    item = get_item(aws_env["table_name"], "evt-fixture-0001")
    assert item["data"]["M"]["order_id"]["S"] == "ord-1001"  # first write wins


def test_processor_malformed_message_fails_only_that_item(aws_env):
    result = processor.handler(load_fixture("sqs_event_malformed.json"))

    # Partial batch response: exactly the malformed message is reported back
    # for retry/DLQ; the good message in the same batch still succeeds.
    assert result == {"batchItemFailures": [{"itemIdentifier": "fixture-message-malformed"}]}
    item = get_item(aws_env["table_name"], "evt-fixture-good")
    assert item is not None
    assert item["type"]["S"] == "user.registered"


def test_processor_propagates_correlation_id_to_logs(aws_env):
    import io
    import logging

    from lib.logging_setup import JsonFormatter

    # Attach a capturing handler alongside the real one and render records
    # with the same JSON formatter the Lambda uses in production.
    stream = io.StringIO()
    capture = logging.StreamHandler(stream)
    capture.setFormatter(JsonFormatter())
    proc_logger = logging.getLogger("processor")
    proc_logger.addHandler(capture)
    try:
        processor.handler(load_fixture("sqs_event.json"))
    finally:
        proc_logger.removeHandler(capture)

    log_lines = [json.loads(line) for line in stream.getvalue().splitlines() if line]
    processed = [e for e in log_lines if e.get("message") == "Event processed"]
    assert processed, "expected an 'Event processed' structured log line"
    assert processed[0]["correlation_id"] == "corr-fixture-0001"
    assert processed[0]["event_id"] == "evt-fixture-0001"
