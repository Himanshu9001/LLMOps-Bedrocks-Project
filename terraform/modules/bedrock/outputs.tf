output "knowledge_base_id" {
  value = aws_bedrockagent_knowledge_base.main.id
}

output "knowledge_base_arn" {
  value = aws_bedrockagent_knowledge_base.main.arn
}

output "data_source_id" {
  value = aws_bedrockagent_data_source.s3.data_source_id
}

output "opensearch_collection_arn" {
  value = aws_opensearchserverless_collection.vectors.arn
}

output "opensearch_collection_endpoint" {
  value = aws_opensearchserverless_collection.vectors.collection_endpoint
}

output "bedrock_kb_role_arn" {
  value = aws_iam_role.bedrock_kb.arn
}