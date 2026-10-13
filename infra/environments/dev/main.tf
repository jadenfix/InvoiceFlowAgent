# InvoiceFlow Agent - Development Environment Infrastructure
# This configuration sets up the core AWS infrastructure for the dev environment

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.0"
    }
  }

  backend "s3" {
    bucket         = "invoiceflow-terraform-state-dev"
    key            = "dev/terraform.tfstate"
    region         = "us-west-2"
    encrypt        = true
    dynamodb_table = "invoiceflow-terraform-locks-dev"
  }
}

# Configure the AWS Provider
provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Environment = var.environment
      Project     = "InvoiceFlow"
      ManagedBy   = "Terraform"
      Owner       = "InvoiceFlow-DevOps"
    }
  }
}

# Data sources
data "aws_availability_zones" "available" {
  state = "available"
}

data "aws_caller_identity" "current" {}

# Local values
locals {
  cluster_name = "${var.project_name}-${var.environment}-cluster"

  common_tags = {
    Environment = var.environment
    Project     = var.project_name
    ManagedBy   = "Terraform"
  }
}

# VPC Module
module "vpc" {
  depends_on = [module.s3]
  source     = "../../modules/vpc"

  project_name         = var.project_name
  environment          = var.environment
  vpc_cidr             = var.vpc_cidr
  flow_log_destination = module.s3.flow_log_destination

  availability_zones = slice(data.aws_availability_zones.available.names, 0, 3)

  tags = local.common_tags
}

# EKS Module
module "eks" {
  source = "../../modules/eks"

  cluster_name    = local.cluster_name
  cluster_version = var.eks_cluster_version

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids

  node_groups       = var.eks_node_groups
  s3_prefix_list_id = module.vpc.s3_endpoint_prefix_list_id

  tags = local.common_tags

  depends_on = [module.vpc]
}

# RDS Module
module "rds" {
  source = "../../modules/rds"

  project_name = var.project_name
  environment  = var.environment

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnet_ids

  engine_version    = var.rds_engine_version
  instance_class    = var.rds_instance_class
  allocated_storage = var.rds_allocated_storage

  database_name   = var.rds_database_name
  master_username = var.rds_master_username

  backup_retention_period = var.rds_backup_retention_period
  backup_window           = var.rds_backup_window
  maintenance_window      = var.rds_maintenance_window

  tags = local.common_tags

  depends_on = [module.vpc]
}

# S3 Module
module "s3" {
  source = "../../modules/s3"

  project_name = var.project_name
  environment  = var.environment

  tags = local.common_tags
}

# Security Groups
resource "aws_security_group" "application_load_balancer" {
  description = "Trusted clients to application HTTPS and HTTP redirect"
  name_prefix = "${var.project_name}-${var.environment}-alb-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description = "HTTP redirect from explicitly trusted clients"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.allowed_ingress_cidrs
  }

  ingress {
    description = "HTTPS from explicitly trusted clients"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = var.allowed_ingress_cidrs
  }

  egress {
    description = "Application targets inside the VPC"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }

  tags = merge(local.common_tags, {
    Name = "${var.project_name}-${var.environment}-alb-sg"
  })
}

module "application_log_key" {
  source           = "../../modules/cloudwatch_key"
  name             = "${var.project_name}-${var.environment}-application"
  log_group_prefix = "/aws/invoiceflow/${var.environment}/"
  tags             = local.common_tags
}

# CloudWatch Log Groups
resource "aws_cloudwatch_log_group" "application_logs" {
  name              = "/aws/invoiceflow/${var.environment}/application"
  retention_in_days = 365
  kms_key_id        = module.application_log_key.key_arn

  tags = local.common_tags
}

resource "aws_cloudwatch_log_group" "infrastructure_logs" {
  name              = "/aws/invoiceflow/${var.environment}/infrastructure"
  retention_in_days = 365
  kms_key_id        = module.application_log_key.key_arn

  tags = local.common_tags
} 