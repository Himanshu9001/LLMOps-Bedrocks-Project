# terraform/modules/s3/main.tf
# Creates all S3 buckets needed for the LLMOps platform.
# Separate bucket per data category — raw docs, processed, eval datasets,
# prompt versions, and Terraform state.
# All buckets: versioning enabled, SSE-S3, public access blocked.

locals {
  bucket_names = {
    raw       = "${var.project}-${var.env}-raw"
    processed = "${var.project}-${var.env}-processed"
    eval      = "${var.project}-${var.env}-eval-datasets"
    prompts   = "${var.project}-${var.env}-prompt-versions"
    tfstate   = "${var.project}-${var.env}-tfstate"
  }
}

resource "aws_s3_bucket" "buckets" {
  for_each = local.bucket_names
  bucket   = each.value

  tags = merge(var.common_tags, {
    Name        = each.value
    bucket_type = each.key
  })
}

# Block all public access on every bucket
resource "aws_s3_bucket_public_access_block" "buckets" {
  for_each = aws_s3_bucket.buckets

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Versioning on all buckets — required for prompt version audit trail
resource "aws_s3_bucket_versioning" "buckets" {
  for_each = aws_s3_bucket.buckets

  bucket = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

# SSE-AES256 on all buckets — upgrade to aws:kms in prod for FIPS compliance
resource "aws_s3_bucket_server_side_encryption_configuration" "buckets" {
  for_each = aws_s3_bucket.buckets

  bucket = each.value.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
}

# Lifecycle tiering on raw/ bucket — raw docs grow fast, tier aggressively
# filter {} = apply to all objects in bucket (required by AWS provider v5+)
# Use filter { prefix = "docs/" } to scope only to ingestion pipeline uploads
resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.buckets["raw"].id

  rule {
    id     = "raw-docs-tiering"
    status = "Enabled"

    # Empty filter = apply to ALL objects in this bucket.
    # provider v5+ requires this block explicitly — omitting it causes a plan warning
    # and will be a hard error in a future provider release.
    filter {}

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }
  }
}