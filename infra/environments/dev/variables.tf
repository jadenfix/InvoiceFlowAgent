# Variables for InvoiceFlow Agent Development Environment

# General Configuration
variable "project_name" {
  description = "Name of the project"
  type        = string
  default     = "invoiceflow"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "dev"
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
  default     = "10.0.0.0/16"
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
      desired_capacity = 2
      max_capacity     = 5
      min_capacity     = 1
      instance_types   = ["t3.medium"]
      capacity_type    = "ON_DEMAND"
      labels = {
        role = "general"
      }
      taints = []
    }
    compute = {
      desired_capacity = 1
      max_capacity     = 3
      min_capacity     = 0
      instance_types   = ["c5.large"]
      capacity_type    = "SPOT"
      labels = {
        role = "compute-intensive"
      }
      taints = [{
        key    = "compute-intensive"
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
  default     = "db.t3.micro"
}

variable "rds_allocated_storage" {
  description = "The allocated storage in gigabytes"
  type        = number
  default     = 20
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
  default     = 7
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
  default     = 30
}

# Security Configuration
variable "allowed_cidr_blocks" {
  description = "List of CIDR blocks allowed to access the infrastructure"
  type        = list(string)
  default     = ["0.0.0.0/0"]  # In production, this should be restricted
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
  default     = false  # Disabled in dev for cost optimization
} 