variable "project" {
  type        = string
  description = "Project name — used as prefix in all resource names"
  default     = "llmops-bedrock"
}

variable "env" {
  type        = string
  description = "Deployment environment"
  default     = "dev"
}

variable "aws_region" {
  type        = string
  description = "Primary AWS region"
  default     = "us-east-1"
}

variable "vpc_cidr" {
  type        = string
  description = "VPC CIDR block"
  default     = "10.0.0.0/16"
}

variable "azs" {
  type        = list(string)
  description = "Availability zones — keep to 2 for dev (cost), 3 for prod"
  default     = ["us-east-1a", "us-east-1b"]
}

variable "public_subnet_cidrs" {
  type        = list(string)
  description = "Public subnet CIDRs — must match length of azs"
  default     = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  type        = list(string)
  description = "Private subnet CIDRs — must match length of azs"
  default     = ["10.0.10.0/24", "10.0.11.0/24"]
}

variable "github_org" {
  type    = string
  default = "Himanshu9001"
}

variable "github_repo" {
  type    = string
  default = "LLMOps-Bedrocks-Project"
}

variable "kubernetes_version" {
  type    = string
  default = "1.31"
}