# ---------------------------------------------------------------------------
# Event queue + dead-letter queue.
#
# Delivery semantics: SQS is at-least-once, so the processor is built to be
# idempotent (see src/processor.py). A message that fails processing is
# retried until maxReceiveCount trips, then SQS moves it to the DLQ — where
# the depth alarm in monitoring.tf pages a human instead of the failure
# disappearing silently.
# ---------------------------------------------------------------------------

resource "aws_sqs_queue" "dlq" {
  name                      = "${local.name_prefix}-events-dlq"
  message_retention_seconds = 1209600 # 14 days: plenty of time to inspect + redrive
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "events" {
  name = "${local.name_prefix}-events"

  # Must exceed the processor's timeout several times over (AWS recommends
  # 6x the function timeout) so a message never becomes visible again while
  # it is still being processed.
  visibility_timeout_seconds = var.lambda_timeout_seconds * 6

  message_retention_seconds = 345600 # 4 days
  sqs_managed_sse_enabled   = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.sqs_max_receive_count
  })
}

# Explicitly allow the main queue (and only it) to send into the DLQ, and
# make future redrives back to the main queue a one-line change.
resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  queue_url = aws_sqs_queue.dlq.id

  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.events.arn]
  })
}
