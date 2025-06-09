# Variables for InvoiceFlow Agent Production Environment

# General Configuration
variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "invoiceflow"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-west-2"
}

# VPC Configuration
variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.2.0.0/16"  # Different CIDR from dev and staging
}

# EKS Configuration
variable "eks_cluster_version" {
  description = "Kubernetes version to use for the EKS cluster"
  type        = string
  default     = "1.28"
}

variable "eks_node_groups" {
  description = "EKS managed node groups configuration"
  type = map(object({
    desired_capacity = number
    max_capacity     = number
    min_capacity     = number
    instance_types   = list(string)
    capacity_type    = string
    labels          = map(string)
    taints = list(object({
      key    = string
      value  = string
      effect = string
    }))
  }))
  default = {
    general = {
      desired_capacity = 6   # High availability
      max_capacity     = 15
      min_capacity     = 3   # Minimum for HA across 3 AZs
      instance_types   = ["m5.xlarge", "m5.2xlarge"]  # Production-grade instances
      capacity_type    = "ON_DEMAND"
      labels = {
        role = "general"
      }
      taints = []
    }
    compute = {
      desired_capacity = 3
      max_capacity     = 10
      min_capacity     = 2
      instance_types   = ["c5.2xlarge", "c5.4xlarge"]  # High-performance compute
      capacity_type    = "ON_DEMAND"  # ON_DEMAND for production reliability
      labels = {
        role = "compute-intensive"
      }
      taints = [{
        key    = "compute-intensive"
        value  = "true"
        effect = "NO_SCHEDULE"
      }]
    }
    memory_optimized = {
      desired_capacity = 2
      max_capacity     = 6
      min_capacity     = 1
      instance_types   = ["r5.xlarge", "r5.2xlarge"]  # Memory-optimized for AI workloads
      capacity_type    = "ON_DEMAND"
      labels = {
        role = "memory-intensive"
      }
      taints = [{
        key    = "memory-intensive"
        value  = "true"
        effect = "NO_SCHEDULE"
      }]
    }
  }
}

# RDS Configuration
variable "rds_engine_version" {
  description = "PostgreSQL engine version"
  type        = string
  default     = "15.4"
}

variable "rds_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.r6g.xlarge"  # Production-grade instance
}

variable "rds_allocated_storage" {
  description = "The allocated storage in gigabytes"
  type        = number
  default     = 500  # Production storage
}

variable "rds_database_name" {
  description = "The name of the database"
  type        = string
  default     = "invoiceflow"
}

variable "rds_master_username" {
  description = "Username for the master DB user"
  type        = string
  default     = "invoiceflow_admin"
}

variable "rds_backup_retention_period" {
  description = "The backup retention period"
  type        = number
  default     = 30  # 30 days for production
}

variable "rds_backup_window" {
  description = "The daily time range during which automated backups are created"
  type        = string
  default     = "03:00-04:00"
}

variable "rds_maintenance_window" {
  description = "The window to perform maintenance"
  type        = string
  default     = "sun:04:00-sun:05:00"
}

# Monitoring Configuration
variable "enable_monitoring" {
  description = "Enable enhanced monitoring"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "CloudWatch logs retention in days"
  type        = number
  default     = 365  # 1 year retention for production
}

# Security Configuration
variable "allowed_cidr_blocks" {
  description = "List of CIDR blocks allowed to access the infrastructure"
  type        = list(string)
  default     = ["10.0.0.0/8"]  # Restricted to private networks
}

# Resource Sizing
variable "enable_autoscaling" {
  description = "Enable autoscaling for EKS node groups"
  type        = bool
  default     = true
}

variable "max_pods_per_node" {
  description = "Maximum number of pods per EKS worker node"
  type        = number
  default     = 110
}

# Feature Flags
variable "enable_ssm_parameter_store" {
  description = "Enable AWS Systems Manager Parameter Store for configuration management"
  type        = bool
  default     = true
}

variable "enable_secrets_manager" {
  description = "Enable AWS Secrets Manager for sensitive data"
  type        = bool
  default     = true
}

variable "enable_cloudtrail" {
  description = "Enable AWS CloudTrail for audit logging"
  type        = bool
  default     = true
}

variable "enable_config" {
  description = "Enable AWS Config for compliance monitoring"
  type        = bool
  default     = true
}

variable "enable_guardduty" {
  description = "Enable AWS GuardDuty for threat detection"
  type        = bool
  default     = true
}

variable "enable_security_hub" {
  description = "Enable AWS Security Hub for security posture management"
  type        = bool
  default     = true
}

# Multi-AZ and Cross-Region Configuration
variable "enable_cross_region_backup" {
  description = "Enable cross-region backup for disaster recovery"
  type        = bool
  default     = true
}

variable "backup_region" {
  description = "AWS region for cross-region backups"
  type        = string
  default     = "us-east-1"
}

# Performance and Scaling
variable "enable_performance_insights" {
  description = "Enable Performance Insights for RDS"
  type        = bool
  default     = true
}

variable "performance_insights_retention_period" {
  description = "Amount of time in days to retain Performance Insights data"
  type        = number
  default     = 731  # 2 years
} 