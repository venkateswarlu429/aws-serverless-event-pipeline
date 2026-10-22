output "api_endpoint" {
  description = "Base URL of the HTTP API. POST events to <endpoint>/events."
  value       = aws_apigatewayv2_api.http.api_endpoint
}

output "events_queue_url" {
  description = "URL of the main events queue."
  value       = aws_sqs_queue.events.id
}

output "events_queue_arn" {
  description = "ARN of the main events queue."
  value       = aws_sqs_queue.events.arn
}

output "dlq_url" {
  description = "URL of the dead-letter queue."
  value       = aws_sqs_queue.dlq.id
}

output "dynamodb_table_name" {
  description = "Name of the events table."
  value       = aws_dynamodb_table.events.name
}

output "alerts_topic_arn" {
  description = "ARN of the SNS topic CloudWatch alarms publish to."
  value       = aws_sns_topic.alerts.arn
}

output "ingest_function_name" {
  description = "Ingest Lambda function name."
  value       = aws_lambda_function.ingest.function_name
}

output "processor_function_name" {
  description = "Processor Lambda function name."
  value       = aws_lambda_function.processor.function_name
}
