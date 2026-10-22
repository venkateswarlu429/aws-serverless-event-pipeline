"""Shared helpers for the serverless event pipeline Lambdas.

Keeping logging / validation / responses in one package means both handlers
emit identically-shaped logs and API responses, which matters when you are
correlating a request across API Gateway -> SQS -> Lambda -> DynamoDB.
"""

from .logging_setup import configure_logger, get_correlation_id, set_correlation_id
from .responses import error_response, json_response
from .validation import ValidationError, validate_event_payload

__all__ = [
    "configure_logger",
    "get_correlation_id",
    "set_correlation_id",
    "error_response",
    "json_response",
    "ValidationError",
    "validate_event_payload",
]
