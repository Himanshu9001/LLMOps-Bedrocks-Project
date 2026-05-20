#!/usr/bin/env bash
# bootstrap.sh
# Run ONCE before the first `terraform init`.
# Creates the S3 state bucket and DynamoDB lock table that the backend config references.
# These resources cannot be managed by Terraform themselves (chicken-and-egg problem).
#
# Usage: bash scripts/bootstrap.sh
# Prerequisites: AWS CLI configured with sufficient IAM permissions

set -euo pipefail

AWS_REGION="us-east-1"
STATE_BUCKET="llmops-bedrock-tfstate"
LOCK_TABLE="llmops-bedrock-tfstate-lock"

echo "==> Bootstrapping Terraform remote state..."
echo "    Region : $AWS_REGION"
echo "    Bucket : $STATE_BUCKET"
echo "    Table  : $LOCK_TABLE"
echo ""

# ── S3 bucket ──────────────────────────────────────────────────────────────────
echo "==> Creating S3 state bucket..."

# us-east-1 does NOT accept LocationConstraint — all other regions require it
if [ "$AWS_REGION" = "us-east-1" ]; then
  aws s3api create-bucket \
    --bucket "$STATE_BUCKET" \
    --region "$AWS_REGION"
else
  aws s3api create-bucket \
    --bucket "$STATE_BUCKET" \
    --region "$AWS_REGION" \
    --create-bucket-configuration LocationConstraint="$AWS_REGION"
fi

echo "==> Enabling versioning on state bucket..."
aws s3api put-bucket-versioning \
  --bucket "$STATE_BUCKET" \
  --versioning-configuration Status=Enabled

echo "==> Enabling encryption on state bucket..."
aws s3api put-bucket-encryption \
  --bucket "$STATE_BUCKET" \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      }
    }]
  }'

echo "==> Blocking public access on state bucket..."
aws s3api put-public-access-block \
  --bucket "$STATE_BUCKET" \
  --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# ── DynamoDB table ─────────────────────────────────────────────────────────────
echo "==> Creating DynamoDB lock table..."
aws dynamodb create-table \
  --table-name "$LOCK_TABLE" \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "$AWS_REGION"

echo ""
echo "✅ Bootstrap complete."
echo ""
echo "Next steps:"
echo "  cd terraform/live/dev"
echo "  terraform init"
echo "  terraform plan -var-file=terraform.tfvars"
echo "  terraform apply -var-file=terraform.tfvars"
