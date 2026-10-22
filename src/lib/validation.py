"""Input validation for events entering the pipeline.

The contract is deliberately small and explicit — a hand-rolled validator is
easier to audit (and has zero dependencies) compared to pulling in a schema
library for three fields. If the contract grows, this is the one module to
swap for jsonschema/pydantic.
"""

# Event types this pipeline accepts. Anything else is a client error (400),
# not something the processor should discover later from the DLQ.
ALLOWED_EVENT_TYPES = frozenset(
    {"order.created", "order.updated", "user.registered", "payment.captured"}
)

MAX_DATA_BYTES = 32 * 1024  # keep messages comfortably under SQS's 256 KB cap


class ValidationError(ValueError):
    """Raised when an inbound event does not match the expected schema."""


def validate_event_payload(payload) -> dict:
    """Validate a decoded JSON body and return a normalised event dict.

    Expected shape::

        {"type": "order.created", "data": {...}, "source": "web"}  # source optional

    Raises ValidationError with a client-safe message on any mismatch.
    """
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object.")

    event_type = payload.get("type")
    if not isinstance(event_type, str) or not event_type:
        raise ValidationError("Field 'type' is required and must be a string.")
    if event_type not in ALLOWED_EVENT_TYPES:
        raise ValidationError(
            f"Unsupported event type '{event_type}'. "
            f"Allowed: {sorted(ALLOWED_EVENT_TYPES)}."
        )

    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValidationError("Field 'data' is required and must be a JSON object.")
    if len(str(data)) > MAX_DATA_BYTES:
        raise ValidationError("Field 'data' exceeds the maximum size.")

    source = payload.get("source", "unknown")
    if not isinstance(source, str):
        raise ValidationError("Field 'source' must be a string when provided.")

    return {"type": event_type, "data": data, "source": source}
