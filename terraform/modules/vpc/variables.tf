variable "project" {
  type        = string
  description = "Project name prefix used in all resource names"
}

variable "env" {
  type        = string
  description = "Environment: dev | staging | prod"
}

variable "aws_region" {
  type        = string
  description = "AWS region to deploy into"
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block for the VPC"
}

variable "azs" {
  type        = list(string)
  description = "List of availability zones (must match subnet CIDR counts)"
}

variable "public_subnet_cidrs" {
  type        = list(string)
  description = "CIDRs for public subnets — one per AZ"
}

variable "private_subnet_cidrs" {
  type        = list(string)
  description = "CIDRs for private subnets — one per AZ"
}

variable "common_tags" {
  type        = map(string)
  description = "Tags applied to every resource in this module"
  default     = {}
}
