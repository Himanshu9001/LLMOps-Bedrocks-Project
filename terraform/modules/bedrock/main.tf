# Bedrock Module
# Creates:
# 1. OpenSearch Serverless collection — vector store for Knowledge Base
# 2. Bedrock Knowledge Base — wired to OpenSearch + Titan Embeddings v2
# 3. Bedrock Knowledge Base Data Source — points to S3 raw bucket
# OpenSearch Serverless requires 3 separate policy resources:
# encryption policy, network policy, data access policy — all mandatory.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ── 1. OpenSearch Serverless — Encryption Policy ──────────────────────────────
# Required before collection can be created — enforces SSE on the collection
resource "aws_opensearchserverless_security_policy" "encryption" {
  name        = "${var.project}-${var.env}-enc"
  type        = "encryption"
  description = "Encryption policy for LLMOps vector store"

  policy = jsonencode({
    Rules = [{
      ResourceType = "collection"
      Resource     = ["collection/${var.project}-${var.env}-vectors"]
    }]
    AWSOwnedKey = true
  })
}

# ── 2. OpenSearch Serverless — Network Policy ─────────────────────────────────
# Controls whether collection is accessible from public internet or VPC only
resource "aws_opensearchserverless_security_policy" "network" {
  name        = "${var.project}-${var.env}-net"
  type        = "network"
  description = "Network policy for LLMOps vector store"

  policy = jsonencode([{
    Rules = [
      {
        ResourceType = "collection"
        Resource     = ["collection/${var.project}-${var.env}-vectors"]
      },
      {
        ResourceType = "dashboard"
        Resource     = ["collection/${var.project}-${var.env}-vectors"]
      }
    ]
    # AllowFromPublic required for Bedrock Knowledge Base to reach OpenSearch
    # In prod: replace with VPC endpoint access
    AllowFromPublic = true
  }])
}

# ── 3. OpenSearch Serverless Collection ───────────────────────────────────────
# VECTORSEARCH type — optimized for embedding similarity search
# Bedrock Knowledge Base uses this as the vector store backend
resource "aws_opensearchserverless_collection" "vectors" {
  name        = "${var.project}-${var.env}-vectors"
  type        = "VECTORSEARCH"
  description = "Vector store for LLMOps Knowledge Base"

  depends_on = [
    aws_opensearchserverless_security_policy.encryption,
    aws_opensearchserverless_security_policy.network,
  ]

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-vectors" })
}

# ── 4. OpenSearch Serverless — Data Access Policy ─────────────────────────────
# Controls who can read/write indexes in the collection
# Bedrock Knowledge Base role needs full index permissions to create and query indexes
resource "aws_opensearchserverless_access_policy" "bedrock_kb" {
  name        = "${var.project}-${var.env}-kb-access"
  type        = "data"
  description = "Bedrock Knowledge Base access to vector collection"

  policy = jsonencode([{
    Rules = [
      {
        ResourceType = "index"
        Resource     = ["index/${var.project}-${var.env}-vectors/*"]
        Permission   = [
          "aoss:CreateIndex",
          "aoss:DeleteIndex",
          "aoss:UpdateIndex",
          "aoss:DescribeIndex",
          "aoss:ReadDocument",
          "aoss:WriteDocument"
        ]
      },
      {
        ResourceType = "collection"
        Resource     = ["collection/${var.project}-${var.env}-vectors"]
        Permission   = ["aoss:DescribeCollectionItems"]
      }
    ]
    Principal = [
      aws_iam_role.bedrock_kb.arn,
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root",
      "arn:aws:iam::011528270076:user/Himanshu_demo_01"
    ]
  }])
}

# ── 5. IAM Role for Bedrock Knowledge Base ────────────────────────────────────
# Bedrock service assumes this role to read S3 docs + write to OpenSearch
resource "aws_iam_role" "bedrock_kb" {
  name = "${var.project}-${var.env}-bedrock-kb-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "bedrock.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = {
          "aws:SourceAccount" = data.aws_caller_identity.current.account_id
        }
      }
    }]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy" "bedrock_kb" {
  name = "${var.project}-${var.env}-bedrock-kb-policy"
  role = aws_iam_role.bedrock_kb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Read raw documents from S3
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          "arn:aws:s3:::${var.project}-${var.env}-raw",
          "arn:aws:s3:::${var.project}-${var.env}-raw/*"
        ]
      },
      {
        # Access OpenSearch Serverless collection
        Effect   = "Allow"
        Action   = ["aoss:APIAccessAll"]
        Resource = "arn:aws:aoss:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:collection/*"
      },
      {
        # Invoke Titan Embeddings v2 for chunking and embedding
        Effect   = "Allow"
        Action   = ["bedrock:InvokeModel"]
        Resource = "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/amazon.titan-embed-text-v2:0"
      }
    ]
  })
}

# ── 6. Bedrock Knowledge Base ─────────────────────────────────────────────────
# Wires together: S3 source → Titan Embeddings → OpenSearch vector store
# tenant_id as metadata field enforces multi-tenant retrieval isolation
resource "aws_bedrockagent_knowledge_base" "main" {
  name        = "${var.project}-${var.env}-kb"
  description = "LLMOps Knowledge Base — document ingestion + RAG"
  role_arn    = aws_iam_role.bedrock_kb.arn

  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/amazon.titan-embed-text-v2:0"
    }
  }

  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    opensearch_serverless_configuration {
      collection_arn    = aws_opensearchserverless_collection.vectors.arn
      vector_index_name = "llmops-docs"
      field_mapping {
        vector_field   = "embedding"
        text_field     = "text"
        metadata_field = "metadata"
      }
    }
  }

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-kb" })

  depends_on = [
    aws_opensearchserverless_access_policy.bedrock_kb,
    aws_iam_role_policy.bedrock_kb,
  ]
}

# ── 7. Bedrock Knowledge Base Data Source ────────────────────────────────────
# Points KB to the S3 raw bucket — sync job ingests docs from here
# Semantic chunking: Bedrock handles chunk boundaries intelligently
resource "aws_bedrockagent_data_source" "s3" {
  knowledge_base_id = aws_bedrockagent_knowledge_base.main.id
  name              = "${var.project}-${var.env}-s3-source"
  description       = "S3 raw documents data source"

  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn = "arn:aws:s3:::${var.project}-${var.env}-raw"
    }
  }

  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "SEMANTIC"
      semantic_chunking_configuration {
        max_token          = 512
        buffer_size        = 1
        breakpoint_percentile_threshold = 95
      }
    }
  }

  depends_on = [aws_bedrockagent_knowledge_base.main]
}