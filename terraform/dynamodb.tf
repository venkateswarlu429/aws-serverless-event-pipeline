# One row per processed event. event_id is the partition key, which is also
# what makes the processor's conditional write (attribute_not_exists) an
# effective idempotency guard: the same event can never create a second row
# or overwrite the first.
resource "aws_dynamodb_table" "events" {
  name         = "${local.name_prefix}-events"
  billing_mode = "PAY_PER_REQUEST" # pay per write/read; zero cost at rest, scales to zero
  hash_key     = "event_id"

  attribute {
    name = "event_id"
    type = "S"
  }

  # Recover from accidental deletes/corruption up to 35 days back.
  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true # AWS-managed key; switch to a customer KMS key if you need key-level audit
  }

  tags = {
    Name = "${local.name_prefix}-events"
  }
}
