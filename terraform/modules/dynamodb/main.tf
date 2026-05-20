# DynamoDB module
# Creates:
# 1. Terraform state locking table
# 2. prompt_registry table — stores prompt versions, eval scores, environments
# 3. document_metadata table — per-chunk metadata for retrieval context
# 4. eval_results table — evaluation run results per prompt version / model

# Terraform state lock table
resource "aws_dynamodb_table" "tfstate_lock" {
  name         = "${var.project}-${var.env}-tfstate-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-tfstate-lock" })
}

# Prompt registry — version-controlled prompt store
# PK: prompt_id, SK: version allows querying all versions of a prompt
resource "aws_dynamodb_table" "prompt_registry" {
  name         = "${var.project}-${var.env}-prompt-registry"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "prompt_id"
  range_key    = "version"

  attribute {
    name = "prompt_id"
    type = "S"
  }

  attribute {
    name = "version"
    type = "S"
  }

  attribute {
    name = "environment"
    type = "S"
  }

  # GSI to query all prompts by environment (e.g. all prompts in prod)
  global_secondary_index {
    name            = "environment-index"
    hash_key        = "environment"
    range_key       = "version"
    projection_type = "ALL"
  }

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-prompt-registry" })
}

# Document metadata — stores per-chunk metadata for every ingested document
# PK: tenant_id, SK: chunk_id enables fast tenant-scoped queries
resource "aws_dynamodb_table" "document_metadata" {
  name         = "${var.project}-${var.env}-document-metadata"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "tenant_id"
  range_key    = "chunk_id"

  attribute {
    name = "tenant_id"
    type = "S"
  }

  attribute {
    name = "chunk_id"
    type = "S"
  }

  attribute {
    name = "document_type"
    type = "S"
  }

  # GSI to query all chunks of a given document type per tenant
  global_secondary_index {
    name            = "document-type-index"
    hash_key        = "tenant_id"
    range_key       = "document_type"
    projection_type = "ALL"
  }

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-document-metadata" })
}

# Eval results — stores evaluation run output per prompt version and model
resource "aws_dynamodb_table" "eval_results" {
  name         = "${var.project}-${var.env}-eval-results"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "eval_run_id"
  range_key    = "prompt_version"

  attribute {
    name = "eval_run_id"
    type = "S"
  }

  attribute {
    name = "prompt_version"
    type = "S"
  }

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-eval-results" })
}
