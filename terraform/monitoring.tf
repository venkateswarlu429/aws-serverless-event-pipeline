# ---------------------------------------------------------------------------
# Alerting: one SNS topic, alarms chosen for the failure modes that actually
# hurt in this architecture:
#   * anything landing in the DLQ (poison messages / persistent failures)
#   * Lambda errors on either function
#   * Lambda throttles (concurrency saturation hiding as missing events)
#   * oldest message ageing in the main queue (consumer fallen behind)
# ---------------------------------------------------------------------------

resource "aws_sns_topic" "alerts" {
  name = "${local.name_prefix}-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  count = var.alarm_email == "" ? 0 : 1

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alarm_email
}

resource "aws_cloudwatch_metric_alarm" "dlq_depth" {
  alarm_name          = "${local.name_prefix}-dlq-not-empty"
  alarm_description   = "Messages have landed in the ${local.name_prefix} DLQ. Inspect and redrive after fixing the cause."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "ingest_errors" {
  alarm_name          = "${local.name_prefix}-ingest-errors"
  alarm_description   = "The ingest Lambda is erroring; clients may be receiving 5xx."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.ingest.function_name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "processor_errors" {
  alarm_name          = "${local.name_prefix}-processor-errors"
  alarm_description   = "The processor Lambda is erroring at the function level (not per-message failures, which surface via the DLQ)."
  namespace           = "AWS/Lambda"
  metric_name         = "Errors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.processor.function_name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "lambda_throttles" {
  for_each = {
    ingest    = aws_lambda_function.ingest.function_name
    processor = aws_lambda_function.processor.function_name
  }

  alarm_name          = "${local.name_prefix}-${each.key}-throttles"
  alarm_description   = "The ${each.key} Lambda is being throttled; review reserved concurrency / account limits."
  namespace           = "AWS/Lambda"
  metric_name         = "Throttles"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = each.value
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "queue_age" {
  alarm_name          = "${local.name_prefix}-events-ageing"
  alarm_description   = "The oldest message in the events queue is over 15 minutes old; the processor may be down or under-scaled."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateAgeOfOldestMessage"
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 900
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.events.name
  }

  alarm_actions = [aws_sns_topic.alerts.arn]
}
