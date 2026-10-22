variable "project" {
  description = "Short project name used as a prefix for all resources."
  type        = string
  default     = "event-pipeline"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region to deploy into."
  type        = string
  default     = "us-east-1"
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention for Lambda log groups."
  type        = number
  default     = 30
}

variable "lambda_timeout_seconds" {
  description = "Timeout for both Lambda functions. The SQS visibility timeout is derived from this (6x, per AWS guidance)."
  type        = number
  default     = 60
}

variable "sqs_max_receive_count" {
  description = "How many times a message can be received before SQS moves it to the DLQ."
  type        = number
  default     = 3
}

variable "processor_batch_size" {
  description = "Maximum SQS messages per processor invocation. Partial batch responses are enabled, so a larger batch is safe."
  type        = number
  default     = 10
}

variable "alarm_email" {
  description = "Optional email address subscribed to the alerts SNS topic. Leave empty to manage subscriptions yourself."
  type        = string
  default     = ""
}
