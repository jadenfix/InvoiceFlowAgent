# Outputs for InvoiceFlow Agent Staging Environment

# VPC Outputs
output "vpc_id" {
  description = "ID of the VPC"
  value       = module.vpc.vpc_id
}

output "vpc_cidr_block" {
  description = "CIDR block of the VPC"
  value       = module.vpc.vpc_cidr_block
}

output "private_subnet_ids" {
  description = "List of private subnet IDs"
  value       = module.vpc.private_subnet_ids
}

output "public_subnet_ids" {
  description = "List of public subnet IDs"
  value       = module.vpc.public_subnet_ids
}

# EKS Outputs
output "cluster_id" {
  description = "EKS cluster ID"
  value       = module.eks.cluster_id
}

output "cluster_arn" {
  description = "EKS cluster ARN"
  value       = module.eks.cluster_arn
}

output "cluster_endpoint" {
  description = "Endpoint for EKS control plane"
  value       = module.eks.cluster_endpoint
}

output "cluster_security_group_id" {
  description = "Security group ID attached to the EKS cluster"
  value       = module.eks.cluster_security_group_id
}

output "cluster_iam_role_name" {
  description = "IAM role name associated with EKS cluster"
  value       = module.eks.cluster_iam_role_name
}

output "cluster_iam_role_arn" {
  description = "IAM role ARN associated with EKS cluster"
  value       = module.eks.cluster_iam_role_arn
}

output "cluster_certificate_authority_data" {
  description = "Base64 encoded certificate data required to communicate with the cluster"
  value       = module.eks.cluster_certificate_authority_data
}

output "cluster_primary_security_group_id" {
  description = "The cluster primary security group ID created by the EKS cluster"
  value       = module.eks.cluster_primary_security_group_id
}

output "node_groups" {
  description = "EKS node groups"
  value       = module.eks.node_groups
}

# RDS Outputs
output "rds_cluster_endpoint" {
  description = "RDS cluster endpoint"
  value       = module.rds.cluster_endpoint
  sensitive   = true
}

output "rds_cluster_reader_endpoint" {
  description = "RDS cluster reader endpoint"
  value       = module.rds.cluster_reader_endpoint
  sensitive   = true
}

output "rds_cluster_database_name" {
  description = "RDS cluster database name"
  value       = module.rds.cluster_database_name
}

output "rds_cluster_port" {
  description = "RDS cluster port"
  value       = module.rds.cluster_port
}

output "rds_cluster_master_username" {
  description = "RDS cluster master username"
  value       = module.rds.cluster_master_username
  sensitive   = true
}

# S3 Outputs
output "s3_bucket_invoices" {
  description = "Name of the S3 bucket for invoice storage"
  value       = module.s3.bucket_invoices
}

output "s3_bucket_processed_invoices" {
  description = "Name of the S3 bucket for processed invoices"
  value       = module.s3.bucket_processed_invoices
}

output "s3_bucket_logs" {
  description = "Name of the S3 bucket for application logs"
  value       = module.s3.bucket_logs
}

output "s3_bucket_backups" {
  description = "Name of the S3 bucket for backups"
  value       = module.s3.bucket_backups
}

# Security Group Outputs
output "alb_security_group_id" {
  description = "ID of the Application Load Balancer security group"
  value       = aws_security_group.application_load_balancer.id
}

# CloudWatch Outputs
output "application_log_group_name" {
  description = "Name of the CloudWatch log group for application logs"
  value       = aws_cloudwatch_log_group.application_logs.name
}

output "infrastructure_log_group_name" {
  description = "Name of the CloudWatch log group for infrastructure logs"
  value       = aws_cloudwatch_log_group.infrastructure_logs.name
}

# Useful commands for connecting to the cluster
output "configure_kubectl" {
  description = "Command to configure kubectl"
  value       = "aws eks update-kubeconfig --region ${var.aws_region} --name ${local.cluster_name}"
}

# Current AWS Account and Region
output "aws_account_id" {
  description = "AWS account ID"
  value       = data.aws_caller_identity.current.account_id
}

output "aws_region" {
  description = "AWS region"
  value       = var.aws_region
}

# Environment Information
output "environment" {
  description = "Environment name"
  value       = var.environment
}

output "project_name" {
  description = "Project name"
  value       = var.project_name
} 