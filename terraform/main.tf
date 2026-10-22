locals {
  name_prefix = "${var.project}-${var.environment}"

  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
    Repository  = "aws-serverless-event-pipeline"
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
