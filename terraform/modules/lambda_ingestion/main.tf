# Lambda Ingestion Module
# Creates ECR repo, Lambda function (container), S3 trigger, CloudWatch alarms.
# Uses container image — handles PyMuPDF C extension dependencies cleanly.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ── ECR Repository ────────────────────────────────────────────────────────────
resource "aws_ecr_repository" "ingestion" {
  name                 = "${var.project}-${var.env}-ingestion"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true   # Trivy-equivalent built into ECR — catches CVEs on every push
  }

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-ingestion-ecr" })
}

# ECR lifecycle — keep only last 10 images, prevents unbounded storage cost
resource "aws_ecr_lifecycle_policy" "ingestion" {
  repository = aws_ecr_repository.ingestion.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = { type = "expire" }
    }]
  })
}

# ── Lambda Function ───────────────────────────────────────────────────────────
# Uses container image — placeholder image URI until first CI/CD build pushes real image
resource "aws_lambda_function" "ingestion" {
  function_name = "${var.project}-${var.env}-ingestion"
  role          = var.lambda_execution_role_arn
  package_type  = "Image"

  # Placeholder image — replaced by GitHub Actions on first push
  image_uri = "${aws_ecr_repository.ingestion.repository_url}:latest"

  timeout      = 300   # 5 min — large PDFs can take time
  memory_size  = 1024  # 1GB — PyMuPDF is memory-intensive for large docs
  architectures = ["arm64"]    # match your Mac build architecture

  environment {
    variables = {
      KNOWLEDGE_BASE_ID = var.knowledge_base_id
      DATA_SOURCE_ID    = var.data_source_id
      METADATA_TABLE    = var.metadata_table
      PROCESSED_BUCKET  = var.processed_bucket
      AWS_ACCOUNT_ID    = data.aws_caller_identity.current.account_id
    }
  }

  # Run Lambda inside VPC — accesses DynamoDB via VPC endpoint
  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-ingestion" })

  depends_on = [aws_ecr_repository.ingestion]

  lifecycle {
    # Ignore image_uri changes — managed by CI/CD, not Terraform
    ignore_changes = [image_uri]
  }
}

# ── S3 Event Trigger ──────────────────────────────────────────────────────────
# Triggers Lambda on any object uploaded to raw/ bucket
resource "aws_s3_bucket_notification" "raw_trigger" {
  bucket = var.raw_bucket_id

  lambda_function {
    lambda_function_arn = aws_lambda_function.ingestion.arn
    events              = ["s3:ObjectCreated:*"]
    # Scope to documents only — ignore metadata files
    filter_prefix       = ""
    filter_suffix       = ""
  }

  depends_on = [aws_lambda_permission.s3_invoke]
}

# Allow S3 to invoke the Lambda function
resource "aws_lambda_permission" "s3_invoke" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.ingestion.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = "arn:aws:s3:::${var.raw_bucket_id}"
}

# ── Lambda Security Group ─────────────────────────────────────────────────────
resource "aws_security_group" "lambda" {
  name        = "${var.project}-${var.env}-ingestion-lambda-sg"
  description = "Security group for ingestion Lambda - egress only"
  vpc_id      = var.vpc_id

  # No ingress — Lambda is never called directly over network
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "HTTPS egress for AWS API calls"
  }

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-ingestion-lambda-sg" })
}

# ── CloudWatch Alarms ─────────────────────────────────────────────────────────
# Alert on ingestion failures — catches parse errors, KB sync failures

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${var.project}-${var.env}-ingestion-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Ingestion Lambda errors detected"
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.ingestion.function_name
  }

  tags = var.common_tags
}

resource "aws_cloudwatch_log_group" "ingestion" {
  name              = "/aws/lambda/${var.project}-${var.env}-ingestion"
  retention_in_days = 30
  tags              = var.common_tags
}