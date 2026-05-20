variable "project" {
  type = string
}

variable "env" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "lambda_execution_role_arn" {
  type = string
}

variable "knowledge_base_id" {
  type = string
}

variable "data_source_id" {
  type = string
}

variable "metadata_table" {
  type = string
}

variable "raw_bucket_id" {
  type = string
}

variable "processed_bucket" {
  type = string
}

variable "common_tags" {
  type    = map(string)
  default = {}
}
