# ---------------------------------------------------------------------------
# Least-privilege execution roles: one per function, each able to touch only
# the exact resources that function needs. No wildcard resource ARNs.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# --- Ingest: write logs + send to the events queue. Nothing else. ----------
resource "aws_iam_role" "ingest" {
  name               = "${local.name_prefix}-ingest"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "ingest" {
  statement {
    sid       = "WriteOwnLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.ingest.arn}:*"]
  }

  statement {
    sid       = "EnqueueEvents"
    effect    = "Allow"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.events.arn]
  }
}

resource "aws_iam_role_policy" "ingest" {
  name   = "${local.name_prefix}-ingest"
  role   = aws_iam_role.ingest.id
  policy = data.aws_iam_policy_document.ingest.json
}

# --- Processor: consume the queue + conditional writes to the table. ------
resource "aws_iam_role" "processor" {
  name               = "${local.name_prefix}-processor"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "processor" {
  statement {
    sid       = "WriteOwnLogs"
    effect    = "Allow"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.processor.arn}:*"]
  }

  statement {
    sid    = "ConsumeQueue"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.events.arn]
  }

  statement {
    sid       = "WriteEventsTable"
    effect    = "Allow"
    actions   = ["dynamodb:PutItem", "dynamodb:GetItem"]
    resources = [aws_dynamodb_table.events.arn]
  }
}

resource "aws_iam_role_policy" "processor" {
  name   = "${local.name_prefix}-processor"
  role   = aws_iam_role.processor.id
  policy = data.aws_iam_policy_document.processor.json
}
