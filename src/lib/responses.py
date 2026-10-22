"""API Gateway proxy response helpers."""

import json


def json_response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def error_response(status_code: int, message: str, correlation_id: str) -> dict:
    """Uniform error shape so API clients can parse failures predictably."""
    return json_response(
        status_code,
        {"error": message, "correlation_id": correlation_id},
    )
