output "tfstate_lock_table" {
  description = "DynamoDB table name for Terraform state locking"
  value       = aws_dynamodb_table.tfstate_lock.name
}

output "prompt_registry_table" {
  description = "DynamoDB table name for prompt version registry"
  value       = aws_dynamodb_table.prompt_registry.name
}

output "document_metadata_table" {
  description = "DynamoDB table name for document chunk metadata"
  value       = aws_dynamodb_table.document_metadata.name
}

output "eval_results_table" {
  description = "DynamoDB table name for evaluation run results"
  value       = aws_dynamodb_table.eval_results.name
}
