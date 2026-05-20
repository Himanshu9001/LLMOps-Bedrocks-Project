variable "project" {
  type = string
}

variable "env" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "vpc_id" {
  type        = string
  description = "VPC ID from vpc module output"
}

variable "private_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs — EKS nodes always in private subnets"
}

variable "kubernetes_version" {
  type    = string
  default = "1.31"
}

variable "allowed_cidr_blocks" {
  type        = list(string)
  description = "CIDRs allowed to hit EKS public endpoint — restrict to your IP in prod"
  default     = ["0.0.0.0/0"]
}

variable "common_tags" {
  type    = map(string)
  default = {}
}