# Remote state lives in S3 with a DynamoDB lock table.
#
# The values below are PLACEHOLDERS — no real account IDs or bucket names are
# committed to this repo. Create the bucket/table once (see README "Deploy"),
# then either edit these values locally (do not commit real ones back) or pass
# them at init time:
#
#   terraform init \
#     -backend-config="bucket=<your-state-bucket>" \
#     -backend-config="key=aws-serverless-event-pipeline/dev/terraform.tfstate" \
#     -backend-config="region=us-east-1" \
#     -backend-config="dynamodb_table=<your-lock-table>"
terraform {
  backend "s3" {
    bucket         = "REPLACE-ME-terraform-state"
    key            = "aws-serverless-event-pipeline/dev/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "REPLACE-ME-terraform-locks"
    encrypt        = true
  }
}
