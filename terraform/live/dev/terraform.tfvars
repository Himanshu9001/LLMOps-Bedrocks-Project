# Dev environment overrides
# All values here override variable defaults for the dev environment.
# Do NOT commit secrets — use AWS Secrets Manager or environment variables.

project    = "llmops-bedrock"
env        = "dev"
aws_region = "us-east-1"

vpc_cidr             = "10.0.0.0/16"
azs                  = ["us-east-1a", "us-east-1b"]
public_subnet_cidrs  = ["10.0.1.0/24", "10.0.2.0/24"]
private_subnet_cidrs = ["10.0.10.0/24", "10.0.11.0/24"]
