output "function_name" { value = aws_lambda_function.ingestion.function_name }
output "function_arn"  { value = aws_lambda_function.ingestion.arn }
output "ecr_repo_url"  { value = aws_ecr_repository.ingestion.repository_url }