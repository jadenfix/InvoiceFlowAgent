# RDS Module for InvoiceFlow Agent
# Creates a PostgreSQL Aurora cluster with proper security and backup configurations

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.1"
    }
  }
}

# RDS manages and automatically rotates the master secret every seven days.
# https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/rds-secrets-manager.html

# DB Subnet Group
resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-${var.environment}-db-subnet-group"
  subnet_ids = var.subnet_ids

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-db-subnet-group"
  })
}

# Security Group for RDS
resource "aws_security_group" "rds" {
  description = "PostgreSQL access limited to application VPC workloads"
  name_prefix = "${var.project_name}-${var.environment}-rds-"
  vpc_id      = var.vpc_id

  ingress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.main.cidr_block]
    description = "PostgreSQL access from VPC"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [data.aws_vpc.main.cidr_block]
    description = "Database traffic limited to the VPC"
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-rds-sg"
  })
}

# KMS Key for RDS encryption
data "aws_caller_identity" "current" {}

resource "aws_kms_key" "rds" {
  policy                  = jsonencode({ Version = "2012-10-17", Statement = [{ Sid = "EnableAccountIAM", Effect = "Allow", Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }, Action = "kms:*", Resource = "*" }] })
  description             = "RDS encryption key for ${var.project_name}-${var.environment}"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-rds-encryption-key"
  })
}

resource "aws_kms_alias" "rds" {
  name          = "alias/${var.project_name}-${var.environment}-rds"
  target_key_id = aws_kms_key.rds.key_id
}

# Parameter Group
resource "aws_rds_cluster_parameter_group" "main" {
  family      = "aurora-postgresql15"
  name        = "${var.project_name}-${var.environment}-cluster-pg"
  description = "RDS cluster parameter group for ${var.project_name}-${var.environment}"

  parameter {
    name  = "log_statement"
    value = "all"
  }

  parameter {
    name  = "log_min_duration_statement"
    value = "1000" # Log queries longer than 1 second
  }

  parameter {
    name  = "shared_preload_libraries"
    value = "pg_stat_statements"
  }

  tags = var.tags
}

resource "aws_db_parameter_group" "main" {
  family = "aurora-postgresql15"
  name   = "${var.project_name}-${var.environment}-db-pg"

  parameter {
    name  = "log_statement"
    value = "all"
  }

  tags = var.tags
}

# RDS Aurora Cluster
resource "aws_rds_cluster" "main" {
  cluster_identifier = "${var.project_name}-${var.environment}-cluster"

  engine                              = "aurora-postgresql"
  engine_version                      = var.engine_version
  database_name                       = var.database_name
  master_username                     = var.master_username
  manage_master_user_password         = true
  master_user_secret_kms_key_id       = aws_kms_key.rds.arn
  iam_database_authentication_enabled = true
  copy_tags_to_snapshot               = true

  backup_retention_period      = var.backup_retention_period
  preferred_backup_window      = var.backup_window
  preferred_maintenance_window = var.maintenance_window

  db_cluster_parameter_group_name = aws_rds_cluster_parameter_group.main.name
  db_subnet_group_name            = aws_db_subnet_group.main.name
  vpc_security_group_ids          = [aws_security_group.rds.id]

  storage_encrypted = true
  kms_key_id        = aws_kms_key.rds.arn

  # Enable logging
  enabled_cloudwatch_logs_exports = ["postgresql"]

  # Enable backtrack (if supported)
  # backtrack_window = 24

  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.project_name}-${var.environment}-final-snapshot"

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-aurora-cluster"
  })
}

# RDS Aurora Instances
resource "aws_rds_cluster_instance" "cluster_instances" {
  count              = var.environment == "prod" ? 2 : 1
  identifier         = "${var.project_name}-${var.environment}-${count.index}"
  cluster_identifier = aws_rds_cluster.main.id
  instance_class     = var.instance_class
  engine             = aws_rds_cluster.main.engine
  engine_version     = aws_rds_cluster.main.engine_version

  db_parameter_group_name = aws_db_parameter_group.main.name

  performance_insights_enabled    = true
  performance_insights_kms_key_id = aws_kms_key.rds.arn
  auto_minor_version_upgrade      = true
  monitoring_interval             = 60
  monitoring_role_arn             = aws_iam_role.rds_enhanced_monitoring.arn

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-aurora-instance-${count.index}"
  })
}

# IAM Role for Enhanced Monitoring
resource "aws_iam_role" "rds_enhanced_monitoring" {
  name = "${var.project_name}-${var.environment}-rds-enhanced-monitoring"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "monitoring.rds.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "rds_enhanced_monitoring" {
  role       = aws_iam_role.rds_enhanced_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

module "database_log_key" {
  source           = "../cloudwatch_key"
  name             = "${var.project_name}-${var.environment}-database"
  log_group_prefix = "/aws/rds/cluster/"
  tags             = var.tags
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "rds" {
  name              = "/aws/rds/cluster/${aws_rds_cluster.main.cluster_identifier}/postgresql"
  retention_in_days = 365
  kms_key_id        = module.database_log_key.key_arn

  tags = var.tags
}

# Data source for VPC
data "aws_vpc" "main" {
  id = var.vpc_id
}
# Independent durable recovery copies in addition to Aurora automated snapshots.
resource "aws_backup_vault" "database" {
  name        = "${var.project_name}-${var.environment}-database"
  kms_key_arn = aws_kms_key.rds.arn
  tags        = var.tags
}
resource "aws_backup_plan" "database" {
  name = "${var.project_name}-${var.environment}-database"
  rule {
    rule_name         = "daily_database_recovery"
    target_vault_name = aws_backup_vault.database.name
    schedule          = "cron(0 5 * * ? *)"
    start_window      = 60
    completion_window = 180
    lifecycle { delete_after = 35 }
  }
  tags = var.tags
}
resource "aws_iam_role" "backup" {
  name               = "${var.project_name}-${var.environment}-database-backup"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "backup.amazonaws.com" }, Action = "sts:AssumeRole", Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }, ArnLike = { "aws:SourceArn" = "arn:aws:backup:*:${data.aws_caller_identity.current.account_id}:*" } } }] })
  tags               = var.tags
}
resource "aws_iam_role_policy_attachment" "backup" {
  role       = aws_iam_role.backup.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSBackupServiceRolePolicyForBackup"
}
resource "aws_backup_selection" "database" {
  name         = "${var.project_name}-${var.environment}-database"
  plan_id      = aws_backup_plan.database.id
  iam_role_arn = aws_iam_role.backup.arn
  resources    = [aws_rds_cluster.main.arn]
  depends_on   = [aws_iam_role_policy_attachment.backup]
}
