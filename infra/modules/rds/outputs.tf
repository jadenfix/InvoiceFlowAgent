output "cluster_endpoint" {
  description = "RDS cluster endpoint"
  value       = aws_rds_cluster.main.endpoint
}

output "cluster_reader_endpoint" {
  description = "RDS cluster reader endpoint"
  value       = aws_rds_cluster.main.reader_endpoint
}

output "cluster_database_name" {
  description = "RDS cluster database name"
  value       = aws_rds_cluster.main.database_name
}

output "cluster_port" {
  description = "RDS cluster port"
  value       = aws_rds_cluster.main.port
}

output "cluster_master_username" {
  description = "RDS cluster master username"
  value       = aws_rds_cluster.main.master_username
}

output "cluster_identifier" {
  description = "RDS cluster identifier"
  value       = aws_rds_cluster.main.cluster_identifier
}

output "cluster_arn" {
  description = "RDS cluster ARN"
  value       = aws_rds_cluster.main.arn
}

output "cluster_members" {
  description = "List of RDS instances that are a part of this cluster"
  value       = aws_rds_cluster.main.cluster_members
}

output "cluster_resource_id" {
  description = "RDS cluster resource ID"
  value       = aws_rds_cluster.main.cluster_resource_id
}

output "security_group_id" {
  description = "ID of the security group"
  value       = aws_security_group.rds.id
}

output "subnet_group_name" {
  description = "Name of the DB subnet group"
  value       = aws_db_subnet_group.main.name
}

output "kms_key_id" {
  description = "The KMS key identifier used for encrypting the RDS cluster"
  value       = aws_kms_key.rds.key_id
}

output "secrets_manager_secret_arn" {
  description = "ARN of the Secrets Manager secret containing the RDS password"
  value       = aws_secretsmanager_secret.rds_password.arn
}

output "enhanced_monitoring_iam_role_arn" {
  description = "ARN of the IAM role for enhanced monitoring"
  value       = aws_iam_role.rds_enhanced_monitoring.arn
} 