variable "project" {
  type = string
}

variable "env" {
  type = string
}

variable "common_tags" {
  type    = map(string)
  default = {}
}

variable "github_org" {
  type        = string
  description = "Your GitHub username or org"
}

variable "github_repo" {
  type        = string
  description = "Repo name: LLMOps-Bedrocks-Project"
}

variable "eks_oidc_provider" {
  type        = string
  default     = ""
  description = "EKS OIDC provider URL — filled after EKS module"
}