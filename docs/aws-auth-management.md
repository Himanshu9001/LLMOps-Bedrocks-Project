# EKS aws-auth ConfigMap Management
#
# The aws-auth ConfigMap maps IAM roles/users to Kubernetes RBAC.
# Managed outside Terraform by convention (eksctl create iamidentitymapping).
#
# Current mappings (as of 2026-05-21):
#
# 1. Node group role (auto-added by EKS)
#    IAM Role: arn:aws:iam::011528270076:role/llmops-bedrock-dev-node-role
#    K8s User:  system:node:{{EC2PrivateDNSName}}
#    K8s Group: system:bootstrappers, system:nodes
#
# 2. GitHub Actions role (added via eksctl)
#    IAM Role: arn:aws:iam::011528270076:role/llmops-bedrock-dev-github-actions-role
#    K8s User:  github-actions
#    K8s Group: system:masters
#
# To add a new mapping:
#   eksctl create iamidentitymapping \
#     --cluster llmops-bedrock-dev \
#     --region us-east-1 \
#     --arn <ROLE_ARN> \
#     --username <k8s-username> \
#     --group system:masters
#
# To view current mappings:
#   kubectl get configmap aws-auth -n kube-system -o yaml
#
# NOTE: In production, use the aws-auth Terraform module:
#   https://registry.terraform.io/modules/terraform-aws-modules/eks/aws/latest
#   It manages aws-auth as a Kubernetes ConfigMap resource via the kubernetes provider.
#
# Why not Terraform here:
#   Managing aws-auth via Terraform requires the kubernetes provider,
#   which requires the cluster to exist first (chicken-and-egg on first apply).
#   eksctl handles this ordering automatically.
