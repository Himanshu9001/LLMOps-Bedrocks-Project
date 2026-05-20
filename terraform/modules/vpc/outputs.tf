output "vpc_id" {
  description = "ID of the created VPC"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "List of public subnet IDs"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "List of private subnet IDs"
  value       = aws_subnet.private[*].id
}

output "vpce_sg_id" {
  description = "Security group ID attached to all Interface VPC endpoints"
  value       = aws_security_group.vpce.id
}

output "nat_gateway_id" {
  description = "NAT Gateway ID (used for egress from private subnets)"
  value       = aws_nat_gateway.main.id
}
