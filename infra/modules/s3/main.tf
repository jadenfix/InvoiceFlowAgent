# S3 Module for InvoiceFlow Agent
# Creates S3 buckets for invoice storage, processed data, logs, and backups

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# KMS Key for S3 encryption
resource "aws_kms_key" "s3" {
  description             = "S3 encryption key for ${var.project_name}-${var.environment}"
  deletion_window_in_days = 7
  enable_key_rotation     = true
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "EnableAccountIAM", Effect = "Allow", Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" }, Action = "kms:*", Resource = "*" },
      { Sid = "CloudTrailEncryption", Effect = "Allow", Principal = { Service = "cloudtrail.amazonaws.com" }, Action = ["kms:GenerateDataKey*", "kms:DescribeKey"], Resource = "*", Condition = { StringEquals = { "aws:SourceArn" = "arn:aws:cloudtrail:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:trail/${var.project_name}-${var.environment}-s3-cloudtrail" } } },
      { Sid = "FlowLogDeliveryEncryption", Effect = "Allow", Principal = { Service = "delivery.logs.amazonaws.com" }, Action = ["kms:GenerateDataKey*", "kms:Decrypt"], Resource = "*", Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }, StringLike = { "kms:EncryptionContext:aws:s3:arn" = "${aws_s3_bucket.logs.arn}/*" } } }
    ]
  })

  tags = merge(var.tags, {
    Name = "${var.project_name}-${var.environment}-s3-encryption-key"
  })
}

resource "aws_kms_alias" "s3" {
  name          = "alias/${var.project_name}-${var.environment}-s3"
  target_key_id = aws_kms_key.s3.key_id
}

# S3 Bucket for raw invoices
resource "aws_s3_bucket" "invoices" {
  bucket = "${var.project_name}-${var.environment}-invoices-${data.aws_caller_identity.current.account_id}"

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-invoices"
    Purpose     = "Raw invoice storage"
    Environment = var.environment
  })
}

resource "aws_s3_bucket_versioning" "invoices" {
  bucket = aws_s3_bucket.invoices.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "invoices" {
  bucket = aws_s3_bucket.invoices.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.s3.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "invoices" {
  bucket = aws_s3_bucket.invoices.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "invoices" {
  bucket = aws_s3_bucket.invoices.id

  rule {
    id     = "invoice_lifecycle"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    transition {
      days          = 365
      storage_class = "DEEP_ARCHIVE"
    }

    noncurrent_version_transition {
      noncurrent_days = 30
      storage_class   = "STANDARD_IA"
    }

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}

# S3 Bucket for processed invoices
resource "aws_s3_bucket" "processed_invoices" {
  bucket = "${var.project_name}-${var.environment}-processed-invoices-${data.aws_caller_identity.current.account_id}"

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-processed-invoices"
    Purpose     = "Processed invoice data"
    Environment = var.environment
  })
}

resource "aws_s3_bucket_versioning" "processed_invoices" {
  bucket = aws_s3_bucket.processed_invoices.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "processed_invoices" {
  bucket = aws_s3_bucket.processed_invoices.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.s3.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "processed_invoices" {
  bucket = aws_s3_bucket.processed_invoices.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# S3 Bucket for application logs
resource "aws_s3_bucket" "logs" {
  bucket = "${var.project_name}-${var.environment}-logs-${data.aws_caller_identity.current.account_id}"

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-logs"
    Purpose     = "Application and access logs"
    Environment = var.environment
  })
}

resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.s3.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "logs" {
  bucket = aws_s3_bucket.logs.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    id     = "logs_lifecycle"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    expiration {
      days = 365 # Delete logs after 1 year
    }
  }
}

# S3 Bucket for backups
resource "aws_s3_bucket" "backups" {
  bucket = "${var.project_name}-${var.environment}-backups-${data.aws_caller_identity.current.account_id}"

  tags = merge(var.tags, {
    Name        = "${var.project_name}-${var.environment}-backups"
    Purpose     = "Database and application backups"
    Environment = var.environment
  })
}

resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.s3.arn
      sse_algorithm     = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "backups" {
  bucket = aws_s3_bucket.backups.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    id     = "backups_lifecycle"
    status = "Enabled"

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER"
    }

    transition {
      days          = 365
      storage_class = "DEEP_ARCHIVE"
    }

    noncurrent_version_transition {
      noncurrent_days = 30
      storage_class   = "STANDARD_IA"
    }

    noncurrent_version_expiration {
      noncurrent_days = 365
    }
  }
}

# CloudTrail for S3 access logging
resource "aws_cloudtrail" "s3_access" {
  kms_key_id                    = aws_kms_key.s3.arn
  enable_log_file_validation    = true
  is_multi_region_trail         = true
  include_global_service_events = true
  cloud_watch_logs_group_arn    = "${aws_cloudwatch_log_group.cloudtrail.arn}:*"
  cloud_watch_logs_role_arn     = aws_iam_role.cloudtrail_logs.arn
  name                          = "${var.project_name}-${var.environment}-s3-cloudtrail"
  s3_bucket_name                = aws_s3_bucket.logs.bucket
  s3_key_prefix                 = "cloudtrail/"

  event_selector {
    read_write_type                  = "All"
    include_management_events        = true
    exclude_management_event_sources = []

    data_resource {
      type   = "AWS::S3::Object"
      values = ["${aws_s3_bucket.invoices.arn}/*", "${aws_s3_bucket.processed_invoices.arn}/*", "${aws_s3_bucket.backups.arn}/*"]
    }
  }

  # Audit log reads, not log-delivery writes: including PutObject on the
  # CloudTrail destination produces an endless delivery/data-event feedback loop.
  # https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html
  event_selector {
    read_write_type           = "ReadOnly"
    include_management_events = false
    data_resource {
      type   = "AWS::S3::Object"
      values = ["${aws_s3_bucket.logs.arn}/*", "${aws_s3_bucket.access_log_sink.arn}/*"]
    }
  }

  tags = var.tags

  depends_on = [aws_s3_bucket_policy.cloudtrail_logs, aws_iam_role_policy.cloudtrail_logs]
}

# S3 bucket policy for CloudTrail
resource "aws_s3_bucket_policy" "cloudtrail_logs" {
  bucket = aws_s3_bucket.logs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "FlowLogDeliveryWrite"
        Effect    = "Allow"
        Principal = { Service = "delivery.logs.amazonaws.com" }
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.logs.arn}/vpc-flow/AWSLogs/${data.aws_caller_identity.current.account_id}/*"
        Condition = {
          StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id, "s3:x-amz-acl" = "bucket-owner-full-control" }
          ArnLike      = { "aws:SourceArn" = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:*" }
        }
      },
      {
        Sid       = "FlowLogDeliveryAclCheck"
        Effect    = "Allow"
        Principal = { Service = "delivery.logs.amazonaws.com" }
        Action    = ["s3:GetBucketAcl", "s3:ListBucket"]
        Resource  = aws_s3_bucket.logs.arn
        Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
      },
      {
        Sid    = "AWSCloudTrailAclCheck"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:GetBucketAcl"
        Resource = aws_s3_bucket.logs.arn
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = "arn:aws:cloudtrail:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:trail/${var.project_name}-${var.environment}-s3-cloudtrail"
          }
        }
      },
      {
        Sid    = "AWSCloudTrailWrite"
        Effect = "Allow"
        Principal = {
          Service = "cloudtrail.amazonaws.com"
        }
        Action   = "s3:PutObject"
        Resource = "${aws_s3_bucket.logs.arn}/cloudtrail/*"
        Condition = {
          StringEquals = {
            "s3:x-amz-acl"  = "bucket-owner-full-control"
            "AWS:SourceArn" = "arn:aws:cloudtrail:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:trail/${var.project_name}-${var.environment}-s3-cloudtrail"
          }
        }
      }
    ]
  })
}
resource "aws_s3_bucket_versioning" "logs" {
  bucket = aws_s3_bucket.logs.id
  versioning_configuration { status = "Enabled" }
}
module "cloudtrail_log_key" {
  source           = "../cloudwatch_key"
  name             = "${var.project_name}-${var.environment}-trail"
  log_group_prefix = "/aws/invoiceflow/${var.environment}/cloudtrail"
  tags             = var.tags
}
resource "aws_cloudwatch_log_group" "cloudtrail" {
  name              = "/aws/invoiceflow/${var.environment}/cloudtrail"
  retention_in_days = 365
  kms_key_id        = module.cloudtrail_log_key.key_arn
  tags              = var.tags
}
resource "aws_iam_role" "cloudtrail_logs" {
  name               = "${var.project_name}-${var.environment}-trail-logs"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "cloudtrail.amazonaws.com" }, Action = "sts:AssumeRole" }] })
  tags               = var.tags
}
resource "aws_iam_role_policy" "cloudtrail_logs" {
  role   = aws_iam_role.cloudtrail_logs.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:${aws_cloudwatch_log_group.cloudtrail.name}:log-stream:${data.aws_caller_identity.current.account_id}_CloudTrail_*" }] })
}

# AWS requires SSE-S3 on S3 server-access-log destinations. SSE-KMS delivery is unsupported.
# Logging this sink to itself creates recursive log traffic. CloudTrail audits sink access.
# Official: https://docs.aws.amazon.com/AmazonS3/latest/userguide/enable-server-access-logging.html
# Exceptions apply ONLY to this sink; all source buckets use CMKs and send server access logs here.
#tfsec:ignore:aws-s3-enable-bucket-logging
resource "aws_s3_bucket" "access_log_sink" {
  bucket = "${var.project_name}-${var.environment}-access-logs-${data.aws_caller_identity.current.account_id}"
  tags   = var.tags
}
resource "aws_s3_bucket_versioning" "access_log_sink" {
  bucket = aws_s3_bucket.access_log_sink.id
  versioning_configuration { status = "Enabled" }
}
# AWS service limitation described above: this dedicated sink must use SSE-S3.
#tfsec:ignore:aws-s3-encryption-customer-key
resource "aws_s3_bucket_server_side_encryption_configuration" "access_log_sink" {
  bucket = aws_s3_bucket.access_log_sink.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "AES256" }
  }
}
resource "aws_s3_bucket_public_access_block" "access_log_sink" {
  bucket                  = aws_s3_bucket.access_log_sink.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_lifecycle_configuration" "access_log_sink" {
  bucket = aws_s3_bucket.access_log_sink.id
  rule {
    id     = "access-log-retention"
    status = "Enabled"
    expiration { days = 365 }
    noncurrent_version_expiration { noncurrent_days = 365 }
  }
}
locals {
  audited_buckets = {
    invoices  = aws_s3_bucket.invoices
    processed = aws_s3_bucket.processed_invoices
    logs      = aws_s3_bucket.logs
    backups   = aws_s3_bucket.backups
  }
}
resource "aws_s3_bucket_logging" "invoices" {
  bucket        = aws_s3_bucket.invoices.id
  target_bucket = aws_s3_bucket.access_log_sink.id
  target_prefix = "invoices/"
  depends_on    = [aws_s3_bucket_policy.access_log_sink]
}

resource "aws_s3_bucket_logging" "processed" {
  bucket        = aws_s3_bucket.processed_invoices.id
  target_bucket = aws_s3_bucket.access_log_sink.id
  target_prefix = "processed/"
  depends_on    = [aws_s3_bucket_policy.access_log_sink]
}

resource "aws_s3_bucket_logging" "logs" {
  bucket        = aws_s3_bucket.logs.id
  target_bucket = aws_s3_bucket.access_log_sink.id
  target_prefix = "logs/"
  depends_on    = [aws_s3_bucket_policy.access_log_sink]
}

resource "aws_s3_bucket_logging" "backups" {
  bucket        = aws_s3_bucket.backups.id
  target_bucket = aws_s3_bucket.access_log_sink.id
  target_prefix = "backups/"
  depends_on    = [aws_s3_bucket_policy.access_log_sink]
}
resource "aws_s3_bucket_policy" "access_log_sink" {
  bucket = aws_s3_bucket.access_log_sink.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "TLSOnly", Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.access_log_sink.arn, "${aws_s3_bucket.access_log_sink.arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } },
      { Sid = "ScopedLogDelivery", Effect = "Allow", Principal = { Service = "logging.s3.amazonaws.com" }, Action = "s3:PutObject", Resource = "${aws_s3_bucket.access_log_sink.arn}/*", Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }, ArnLike = { "aws:SourceArn" = [for bucket in local.audited_buckets : bucket.arn] } } }
    ]
  })
}
