output "github_actions_role_arn" {
  value = aws_iam_role.github_actions.arn
}

output "bedrock_invoke_role_arn" {
  value = aws_iam_role.bedrock_invoke.arn
}

output "lambda_execution_role_arn" {
  value = aws_iam_role.lambda_execution.arn
}

output "fastapi_irsa_role_arn" {
  value = aws_iam_role.fastapi_irsa.arn
}
