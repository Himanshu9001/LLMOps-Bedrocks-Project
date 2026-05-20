output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnet IDs — used by EKS, Lambda"
  value       = module.vpc.private_subnet_ids
}

output "public_subnet_ids" {
  description = "Public subnet IDs — used by ALB, NAT GW"
  value       = module.vpc.public_subnet_ids
}

output "s3_bucket_ids" {
  description = "Map of all S3 bucket IDs by type"
  value       = module.s3.bucket_ids
}

output "dynamodb_tables" {
  description = "Map of DynamoDB table names"
  value = {
    tfstate_lock      = module.dynamodb.tfstate_lock_table
    prompt_registry   = module.dynamodb.prompt_registry_table
    document_metadata = module.dynamodb.document_metadata_table
    eval_results      = module.dynamodb.eval_results_table
  }
}

output "iam_roles" {
  value = {
    github_actions   = module.iam.github_actions_role_arn
    bedrock_invoke   = module.iam.bedrock_invoke_role_arn
    lambda_execution = module.iam.lambda_execution_role_arn
    fastapi_irsa     = module.iam.fastapi_irsa_role_arn
  }
}

output "eks_cluster_name" {
  value = module.eks.cluster_name
}

output "eks_oidc_provider_arn" {
  value = module.eks.oidc_provider_arn
}
