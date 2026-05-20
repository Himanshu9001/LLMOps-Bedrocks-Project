# IAM Module — 4 roles: GitHub Actions OIDC, Bedrock invocation, Lambda execution, IRSA for EKS FastAPI pod

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ── 1. GitHub Actions OIDC Role ───────────────────────────────────────────────
# Allows GitHub Actions CI/CD to assume this role via OIDC — no static AWS keys needed

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-github-oidc" })
}

resource "aws_iam_role" "github_actions" {
  name = "${var.project}-${var.env}-github-actions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringLike = {
          # Scoped to your repo only — prevents other GitHub repos assuming this role
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_org}/${var.github_repo}:*"
        }
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-github-actions-role" })
}

# Permissions for GitHub Actions — Terraform plan/apply + ECR push
resource "aws_iam_role_policy" "github_actions" {
  name = "${var.project}-${var.env}-github-actions-policy"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Terraform state read/write
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
        Resource = [
          "arn:aws:s3:::${var.project}-tfstate",
          "arn:aws:s3:::${var.project}-tfstate/*"
        ]
      },
      {
        # S3 lock file for state locking
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:DeleteObject", "s3:GetObject"]
        Resource = "arn:aws:s3:::${var.project}-tfstate/*.tflock"
      },
      {
        # ECR push for FastAPI image — Phase 3
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken", "ecr:BatchCheckLayerAvailability",
                    "ecr:PutImage", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
                    "ecr:CompleteLayerUpload"]
        Resource = "*"
      }
    ]
  })
}

# ── 2. Bedrock Invocation Role ────────────────────────────────────────────────
# Least-privilege: scoped to specific model ARNs only — not bedrock:*

resource "aws_iam_role" "bedrock_invoke" {
  name = "${var.project}-${var.env}-bedrock-invoke-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-bedrock-invoke-role" })
}

resource "aws_iam_role_policy" "bedrock_invoke" {
  name = "${var.project}-${var.env}-bedrock-invoke-policy"
  role = aws_iam_role.bedrock_invoke.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Scoped to Claude Sonnet, Haiku, Nova Pro only — not all Bedrock models
        Effect = "Allow"
        Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
        Resource = [
          "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0",
          "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0",
          "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/amazon.nova-pro-v1:0"
        ]
      },
      {
        # Bedrock Knowledge Base retrieval
        Effect   = "Allow"
        Action   = ["bedrock:Retrieve", "bedrock:RetrieveAndGenerate"]
        Resource = "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:knowledge-base/*"
      },
      {
        # Bedrock Agent invocation
        Effect   = "Allow"
        Action   = ["bedrock:InvokeAgent"]
        Resource = "arn:aws:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:agent-alias/*"
      }
    ]
  })
}

# ── 3. Lambda Execution Role ──────────────────────────────────────────────────
# Used by document ingestion Lambda (Phase 2) — S3 read, DynamoDB write, CloudWatch logs

resource "aws_iam_role" "lambda_execution" {
  name = "${var.project}-${var.env}-lambda-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-lambda-execution-role" })
}

resource "aws_iam_role_policy" "lambda_execution" {
  name = "${var.project}-${var.env}-lambda-execution-policy"
  role = aws_iam_role.lambda_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Read raw docs, write to processed bucket
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
        Resource = [
          "arn:aws:s3:::${var.project}-${var.env}-raw/*",
          "arn:aws:s3:::${var.project}-${var.env}-processed/*",
          "arn:aws:s3:::${var.project}-${var.env}-raw",
          "arn:aws:s3:::${var.project}-${var.env}-processed"
        ]
      },
      {
        # Write chunk metadata to DynamoDB
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:GetItem"]
        Resource = "arn:aws:dynamodb:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:table/${var.project}-${var.env}-document-metadata"
      },
      {
        # CloudWatch logs — required for Lambda to write execution logs
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/*"
      },
      {
        # VPC networking — required when Lambda runs inside VPC
        Effect   = "Allow"
        Action   = ["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface"]
        Resource = "*"
      }
    ]
  })
}

# Attach Bedrock invoke policy to Lambda execution role
# Lambda ingestion function also calls Bedrock for chunking
resource "aws_iam_role_policy_attachment" "lambda_bedrock" {
  role       = aws_iam_role.lambda_execution.name
  policy_arn = aws_iam_policy.bedrock_invoke_managed.arn
}

resource "aws_iam_policy" "bedrock_invoke_managed" {
  name = "${var.project}-${var.env}-bedrock-invoke-managed"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"]
      Resource = [
        "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/anthropic.claude-3-5-sonnet-20241022-v2:0",
        "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0",
        "arn:aws:bedrock:${data.aws_region.current.name}::foundation-model/amazon.nova-pro-v1:0"
      ]
    }]
  })

  tags = var.common_tags
}

# ── 4. IRSA Role — FastAPI Pod on EKS ────────────────────────────────────────
# Allows the FastAPI Kubernetes pod to call Bedrock without any hardcoded credentials
# IRSA = IAM Roles for Service Accounts — pod assumes role via projected service account token

resource "aws_iam_role" "fastapi_irsa" {
  name = "${var.project}-${var.env}-fastapi-irsa-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:oidc-provider/${var.eks_oidc_provider}" }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          # Scoped to fastapi service account in llmops namespace only
          "${var.eks_oidc_provider}:sub" = "system:serviceaccount:llmops:fastapi-sa"
          "${var.eks_oidc_provider}:aud" = "sts.amazonaws.com"
        }
      }
    }]
  })

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-fastapi-irsa-role" })
}

resource "aws_iam_role_policy_attachment" "fastapi_bedrock" {
  role       = aws_iam_role.fastapi_irsa.name
  policy_arn = aws_iam_policy.bedrock_invoke_managed.arn
}

resource "aws_iam_role_policy" "fastapi_redis_secrets" {
  name = "${var.project}-${var.env}-fastapi-secrets-policy"
  role = aws_iam_role.fastapi_irsa.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      # FastAPI reads Redis connection string from Secrets Manager
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:${var.project}-${var.env}-*"
    }]
  })
}