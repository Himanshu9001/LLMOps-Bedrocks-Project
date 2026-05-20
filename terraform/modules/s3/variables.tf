variable "project" {
  type        = string
  description = "Project name prefix"
}

variable "env" {
  type        = string
  description = "Environment: dev | staging | prod"
}

variable "common_tags" {
  type        = map(string)
  description = "Tags applied to every resource"
  default     = {}
}
