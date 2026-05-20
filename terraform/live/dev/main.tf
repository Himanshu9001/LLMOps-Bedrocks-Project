terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # Bootstrap: manually create this bucket + DynamoDB table once before init.
  # See scripts/bootstrap.sh
  backend "s3" {
    bucket       = "llmops-bedrock-tfstate"
    key          = "dev/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true        # replaces deprecated dynamodb_table
    encrypt      = true
  }
}

provider "aws" {
  region = var.aws_region

  # default_tags applies to every resource created by this provider.
  # This is the correct pattern — no need to pass common_tags into every module call.
  default_tags {
    tags = {
      project    = var.project
      env        = var.env
      team       = "llmops"
      managed_by = "terraform"
    }
  }
}

# Local map passed into modules that use merge(var.common_tags, {...}).
# Kept in sync with default_tags above.
locals {
  common_tags = {
    project    = var.project
    env        = var.env
    team       = "llmops"
    managed_by = "terraform"
  }
}

module "vpc" {
  source = "../../modules/vpc"

  project              = var.project
  env                  = var.env
  aws_region           = var.aws_region
  vpc_cidr             = var.vpc_cidr
  azs                  = var.azs
  public_subnet_cidrs  = var.public_subnet_cidrs
  private_subnet_cidrs = var.private_subnet_cidrs
  common_tags          = local.common_tags
}

module "s3" {
  source = "../../modules/s3"

  project     = var.project
  env         = var.env
  common_tags = local.common_tags
}

module "dynamodb" {
  source = "../../modules/dynamodb"

  project     = var.project
  env         = var.env
  common_tags = local.common_tags
}

module "iam" {
  source            = "../../modules/iam"
  project           = var.project
  env               = var.env
  common_tags       = local.common_tags
  github_org        = var.github_org
  github_repo       = var.github_repo
  eks_oidc_provider = module.eks.oidc_provider_url
}

module "eks" {
  source             = "../../modules/eks"
  project            = var.project
  env                = var.env
  aws_region         = var.aws_region
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  common_tags        = local.common_tags
}


module "bedrock" {
  source      = "../../modules/bedrock"
  project     = var.project
  env         = var.env
  common_tags = local.common_tags
}