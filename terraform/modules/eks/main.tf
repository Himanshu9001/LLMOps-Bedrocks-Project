# EKS Module
# Creates EKS cluster with managed node groups for FastAPI + Langfuse.
# Uses managed node groups — AWS handles node provisioning, patching, draining.
# IRSA enabled via OIDC provider — pods get AWS credentials without static keys.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# ── EKS Cluster ───────────────────────────────────────────────────────────────
resource "aws_eks_cluster" "main" {
  name     = "${var.project}-${var.env}"
  version  = var.kubernetes_version
  role_arn = aws_iam_role.eks_cluster.arn

  vpc_config {
    subnet_ids              = var.private_subnet_ids
    endpoint_private_access = true
    endpoint_public_access  = true   # set false in prod, use VPN/bastion
    public_access_cidrs     = var.allowed_cidr_blocks
  }

  # Enable EKS control plane logging — audit logs critical for security
  enabled_cluster_log_types = ["api", "audit", "authenticator", "controllerManager", "scheduler"]

  depends_on = [
    aws_iam_role_policy_attachment.eks_cluster_policy,
    aws_iam_role_policy_attachment.eks_vpc_policy,
  ]

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-eks" })
}

# ── OIDC Provider for IRSA ────────────────────────────────────────────────────
# Extracts the OIDC thumbprint from the cluster and registers it with IAM.
# This is what enables pod-level IAM roles (IRSA) — no static credentials in pods.

data "tls_certificate" "eks" {
  url = aws_eks_cluster.main.identity[0].oidc[0].issuer
}

resource "aws_iam_openid_connect_provider" "eks" {
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.eks.certificates[0].sha1_fingerprint]
  url             = aws_eks_cluster.main.identity[0].oidc[0].issuer

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-eks-oidc" })
}

# ── EKS Cluster IAM Role ──────────────────────────────────────────────────────
resource "aws_iam_role" "eks_cluster" {
  name = "${var.project}-${var.env}-eks-cluster-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "eks.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_iam_role_policy_attachment" "eks_vpc_policy" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSVPCResourceController"
}

# ── Node Group IAM Role ───────────────────────────────────────────────────────
resource "aws_iam_role" "eks_nodes" {
  name = "${var.project}-${var.env}-eks-node-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy_attachment" "eks_worker_node" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "eks_cni" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "eks_ecr_read" {
  role       = aws_iam_role.eks_nodes.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# ── Managed Node Group — system ───────────────────────────────────────────────
# Runs core cluster components: CoreDNS, kube-proxy, ALB controller
# t3.medium = 2 vCPU, 4GB RAM — sufficient for system pods

resource "aws_eks_node_group" "system" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.project}-${var.env}-system"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = var.private_subnet_ids
  instance_types  = ["t3.medium"]
  capacity_type   = "ON_DEMAND"

  scaling_config {
    desired_size = 2
    min_size     = 2
    max_size     = 4
  }

  update_config {
    max_unavailable = 1   # rolling update — always keep 1 node available
  }

  # Taint system nodes — only system pods schedule here
  taint {
    key    = "node-role"
    value  = "system"
    effect = "NO_SCHEDULE"
  }

  labels = {
    role = "system"
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node,
    aws_iam_role_policy_attachment.eks_cni,
    aws_iam_role_policy_attachment.eks_ecr_read,
  ]

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-system-ng" })
}

# ── Managed Node Group — application ─────────────────────────────────────────
# Runs FastAPI + Langfuse workloads
# t3.large = 2 vCPU, 8GB RAM — Langfuse needs ~2GB RAM minimum

resource "aws_eks_node_group" "application" {
  cluster_name    = aws_eks_cluster.main.name
  node_group_name = "${var.project}-${var.env}-application"
  node_role_arn   = aws_iam_role.eks_nodes.arn
  subnet_ids      = var.private_subnet_ids
  instance_types  = ["t3.large"]
  capacity_type   = "ON_DEMAND"

  scaling_config {
    desired_size = 2
    min_size     = 1
    max_size     = 6   # HPA can scale pods, CA scales nodes up to 6
  }

  update_config {
    max_unavailable = 1
  }

  labels = {
    role = "application"
  }

  depends_on = [
    aws_iam_role_policy_attachment.eks_worker_node,
    aws_iam_role_policy_attachment.eks_cni,
    aws_iam_role_policy_attachment.eks_ecr_read,
  ]

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-application-ng" })
}

# ── Security Group for EKS nodes ──────────────────────────────────────────────
resource "aws_security_group" "eks_nodes" {
  name        = "${var.project}-${var.env}-eks-nodes-sg"
  description = "Security group for EKS worker nodes"
  vpc_id      = var.vpc_id

  # Nodes communicate with each other freely
  ingress {
    from_port = 0
    to_port   = 0
    protocol  = "-1"
    self      = true
  }

  # Control plane to node communication
  ingress {
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_cluster.id]
  }

  ingress {
    from_port       = 1025
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [aws_security_group.eks_cluster.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-eks-nodes-sg" })
}

# ── Security Group for EKS control plane ─────────────────────────────────────
resource "aws_security_group" "eks_cluster" {
  name        = "${var.project}-${var.env}-eks-cluster-sg"
  description = "Security group for EKS control plane"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.common_tags, { Name = "${var.project}-${var.env}-eks-cluster-sg" })
}