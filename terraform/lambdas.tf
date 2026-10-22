# The whole src/ directory is the deployment package for BOTH functions — a
# single shared artifact keeps the shared lib/ identical in each function.
# (For functions with diverging dependencies, split into per-function packages
# or switch to a container image; noted in the README.)
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/build/lambda.zip"
  excludes    = ["__pycache__"]
}

resource "aws_cloudwatch_log_group" "ingest" {
  name              = "/aws/lambda/${local.name_prefix}-ingest"
  retention_in_days = var.log_retention_days
}

resource "aws_cloudwatch_log_group" "processor" {
  name              = "/aws/lambda/${local.name_prefix}-processor"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "ingest" {
  function_name = "${local.name_prefix}-ingest"
  description   = "Validates inbound events and enqueues them for async processing."
  role          = aws_iam_role.ingest.arn
  handler       = "ingest.handler"
  runtime       = "python3.12"
  timeout       = var.lambda_timeout_seconds
  memory_size   = 128

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      QUEUE_URL = aws_sqs_queue.events.id
      LOG_LEVEL = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.ingest]
}

resource "aws_lambda_function" "processor" {
  function_name = "${local.name_prefix}-processor"
  description   = "Consumes events from SQS and writes them idempotently to DynamoDB."
  role          = aws_iam_role.processor.arn
  handler       = "processor.handler"
  runtime       = "python3.12"
  timeout       = var.lambda_timeout_seconds
  memory_size   = 256

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.events.name
      LOG_LEVEL  = "INFO"
    }
  }

  depends_on = [aws_cloudwatch_log_group.processor]
}

# SQS -> Lambda trigger. ReportBatchItemFailures is the switch that makes
# Lambda honour the function's {"batchItemFailures": [...]} response and
# delete only the messages that actually succeeded.
resource "aws_lambda_event_source_mapping" "processor_sqs" {
  event_source_arn = aws_sqs_queue.events.arn
  function_name    = aws_lambda_function.processor.arn
  batch_size       = var.processor_batch_size
  enabled          = true

  function_response_types = ["ReportBatchItemFailures"]

  scaling_config {
    maximum_concurrency = 50 # cap parallel consumers; protects downstream quotas
  }
}
