output "bucket_ids" {
  description = "Map of bucket key to bucket ID"
  value       = { for k, v in aws_s3_bucket.buckets : k => v.id }
}

output "bucket_arns" {
  description = "Map of bucket key to bucket ARN"
  value       = { for k, v in aws_s3_bucket.buckets : k => v.arn }
}

output "raw_bucket_id" {
  description = "Raw documents bucket ID — used by Lambda ingestion triggers"
  value       = aws_s3_bucket.buckets["raw"].id
}

output "eval_bucket_id" {
  description = "Eval datasets bucket ID — used by evaluation pipeline"
  value       = aws_s3_bucket.buckets["eval"].id
}

output "prompts_bucket_id" {
  description = "Prompt versions bucket ID — used by prompt management pipeline"
  value       = aws_s3_bucket.buckets["prompts"].id
}
