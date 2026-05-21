# ── GitHub Actions Role — Complete Policy Set ─────────────────────────────────
# These policies were added incrementally during CI/CD setup.
# Consolidated here for reference and future Terraform-managed deploys.

resource "aws_iam_role_policy" "github_actions_eks" {
  name = "${var.project_name}-github-eks-policy"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "eks:DescribeCluster",
        "eks:ListClusters",
        "eks:AccessKubernetesApi"
      ]
      Resource = "arn:aws:eks:${var.aws_region}:${var.aws_account_id}:cluster/${var.project_name}"
    }]
  })
}

resource "aws_iam_role_policy" "github_actions_ecr" {
  name = "${var.project_name}-github-ecr-policy"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:DescribeRepositories",
        "ecr:BatchGetImage"
      ]
      Resource = "*"
    }]
  })
}

resource "aws_iam_role_policy" "github_actions_dynamodb" {
  name = "${var.project_name}-github-dynamodb-policy"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ]
      Resource = [
        "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}-prompt-registry",
        "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}-eval-results",
        "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}-prompt-registry/index/*",
        "arn:aws:dynamodb:${var.aws_region}:${var.aws_account_id}:table/${var.project_name}-eval-results/index/*"
      ]
    }]
  })
}

resource "aws_iam_role_policy" "github_actions_s3" {
  name = "${var.project_name}-github-s3-policy"
  role = aws_iam_role.github_actions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
      Resource = [
        "arn:aws:s3:::${var.project_name}-eval-datasets",
        "arn:aws:s3:::${var.project_name}-eval-datasets/*",
        "arn:aws:s3:::${var.project_name}-prompt-versions",
        "arn:aws:s3:::${var.project_name}-prompt-versions/*"
      ]
    }]
  })
}
