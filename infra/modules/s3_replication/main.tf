# Same-account, one-way cross-region replication. No reverse forwarding or automatic failover.
terraform {
  required_providers {
    aws = {
      source                = "hashicorp/aws"
      version               = "~> 5.0"
      configuration_aliases = [aws.primary, aws.dr]
    }
  }
}
data "aws_caller_identity" "primary" { provider = aws.primary }
data "aws_caller_identity" "dr" { provider = aws.dr }
data "aws_region" "primary" { provider = aws.primary }
data "aws_region" "dr" { provider = aws.dr }
data "aws_partition" "current" { provider = aws.primary }
locals {
  kms_names   = toset(["invoices", "processed", "logs", "backups"])
  kms_sources = { for name in local.kms_names : name => var.source_buckets[name] }

  # Account and region are included in the digest: globally scoped, deterministic, <=63 characters.
  prefix          = "${substr(lower(var.project_name), 0, 12)}-${substr(lower(var.environment), 0, 8)}"
  replica_names   = { for name, bucket in var.source_buckets : name => "${local.prefix}-dr-${substr(replace(name, "_", "-"), 0, 12)}-${substr(sha256("${data.aws_caller_identity.dr.account_id}:${data.aws_region.dr.name}:${var.project_name}:${var.environment}:${name}"), 0, 12)}" }
  access_log_name = "${local.prefix}-dr-access-${substr(sha256("${data.aws_caller_identity.dr.account_id}:${data.aws_region.dr.name}:${var.project_name}:${var.environment}:access-delivery"), 0, 12)}"
  destinations    = merge(aws_s3_bucket.replica, { access_logs = aws_s3_bucket.log_replica })
}

resource "aws_iam_role" "replication" {
  provider = aws.primary
  name     = "${var.project_name}-${var.environment}-s3-crr"
  # This is AWS's documented replication trust policy. Permissions below are bucket/key-scoped.
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "s3.amazonaws.com" }, Action = "sts:AssumeRole" }] })
  tags               = var.tags
}
resource "aws_kms_key" "replica" {
  provider                = aws.dr
  description             = "Regional recovery replica encryption for ${var.project_name}-${var.environment}"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Sid = "DelegateAccountIAM", Effect = "Allow", Principal = { AWS = "arn:${data.aws_partition.current.partition}:iam::${data.aws_caller_identity.dr.account_id}:root" }, Action = "kms:*", Resource = "*" },
    { Sid = "ScopedS3Replication", Effect = "Allow", Principal = { AWS = aws_iam_role.replication.arn }, Action = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"], Resource = "*", Condition = {
      StringEquals = { "kms:ViaService" = "s3.${data.aws_region.dr.name}.${data.aws_partition.current.dns_suffix}" },
      StringLike   = { "kms:EncryptionContext:aws:s3:arn" = flatten([for name in keys(local.kms_sources) : ["arn:${data.aws_partition.current.partition}:s3:::${local.replica_names[name]}", "arn:${data.aws_partition.current.partition}:s3:::${local.replica_names[name]}/*"]]) }
    } }
  ] })
  tags = var.tags
}
resource "aws_kms_alias" "replica" {
  provider      = aws.dr
  name          = "alias/${var.project_name}-${var.environment}-s3-dr"
  target_key_id = aws_kms_key.replica.key_id
}

# CKV_AWS_144 conflicts with a terminal recovery destination: another outbound rule
# would require another recovery region and does not protect incoming replicas.
# These buckets receive actual CRR below; original sources are not exempted.
resource "aws_s3_bucket" "replica" {
  #checkov:skip=CKV_AWS_144:Terminal one-way recovery replicas receive CRR; outbound re-replication is outside this recovery architecture.
  provider = aws.dr
  for_each = local.kms_names
  bucket   = local.replica_names[each.key]
  tags     = merge(var.tags, { RecoveryRole = "terminal-replica", SourceBucket = var.source_buckets[each.key].id })
  lifecycle {
    precondition {
      condition     = data.aws_region.primary.name != data.aws_region.dr.name
      error_message = "Recovery provider must be in a different AWS region."
    }
    precondition {
      condition     = data.aws_caller_identity.primary.account_id == data.aws_caller_identity.dr.account_id
      error_message = "This module supports same-account replication only."
    }
  }
}
# Source access logs require SSE-S3. AWS replication preserves their encryption type,
# regardless of destination defaults. Do not claim CMK encryption for these replicas.
# https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication-config-for-kms-objects.html
#tfsec:ignore:aws-s3-encryption-customer-key
resource "aws_s3_bucket" "log_replica" {
  #checkov:skip=CKV_AWS_144:Terminal recovery copy of source access logs; no reverse or third-region replication.
  #checkov:skip=CKV_AWS_145:AWS replication preserves required SSE-S3 access-log encryption; CMK encryption is not claimed for these replicas.
  provider = aws.dr
  bucket   = local.replica_names["access_logs"]
  tags     = merge(var.tags, { RecoveryRole = "terminal-access-log-replica", SourceBucket = var.source_buckets["access_logs"].id })
  lifecycle {
    precondition {
      condition     = data.aws_region.primary.name != data.aws_region.dr.name && data.aws_caller_identity.primary.account_id == data.aws_caller_identity.dr.account_id
      error_message = "Recovery must use another region in the same AWS account."
    }
  }
}
resource "aws_s3_bucket_versioning" "replica" {
  provider = aws.dr
  for_each = local.kms_names
  bucket   = aws_s3_bucket.replica[each.key].id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_versioning" "log_replica" {
  provider = aws.dr
  bucket   = aws_s3_bucket.log_replica.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "replica" {
  provider = aws.dr
  for_each = local.kms_names
  bucket   = aws_s3_bucket.replica[each.key].id
  rule {
    bucket_key_enabled = false
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.replica.arn
    }
  }
}
#tfsec:ignore:aws-s3-encryption-customer-key
resource "aws_s3_bucket_server_side_encryption_configuration" "log_replica" {
  provider = aws.dr
  bucket   = aws_s3_bucket.log_replica.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
resource "aws_s3_bucket_public_access_block" "replica" {
  provider                = aws.dr
  for_each                = local.kms_names
  bucket                  = aws_s3_bucket.replica[each.key].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_public_access_block" "log_replica" {
  provider                = aws.dr
  bucket                  = aws_s3_bucket.log_replica.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_ownership_controls" "replica" {
  provider = aws.dr
  for_each = local.kms_names
  bucket   = aws_s3_bucket.replica[each.key].id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_ownership_controls" "log_replica" {
  provider = aws.dr
  bucket   = aws_s3_bucket.log_replica.id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_policy" "replica_tls" {
  provider = aws.dr
  for_each = local.kms_names
  bucket   = aws_s3_bucket.replica[each.key].id
  policy   = jsonencode({ Version = "2012-10-17", Statement = [{ Sid = "TLSOnly", Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.replica[each.key].arn, "${aws_s3_bucket.replica[each.key].arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}
resource "aws_s3_bucket_policy" "log_replica_tls" {
  provider = aws.dr
  bucket   = aws_s3_bucket.log_replica.id
  policy   = jsonencode({ Version = "2012-10-17", Statement = [{ Sid = "TLSOnly", Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.log_replica.arn, "${aws_s3_bucket.log_replica.arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}
resource "aws_s3_bucket_lifecycle_configuration" "replica" {
  provider = aws.dr
  for_each = local.kms_names
  bucket   = aws_s3_bucket.replica[each.key].id
  rule {
    id     = "retained-recovery-versions"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
    noncurrent_version_expiration { noncurrent_days = var.noncurrent_retention_days }
  }
  depends_on = [aws_s3_bucket_versioning.replica]
}
resource "aws_s3_bucket_lifecycle_configuration" "log_replica" {
  provider = aws.dr
  bucket   = aws_s3_bucket.log_replica.id
  rule {
    id     = "retained-recovery-versions"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
    noncurrent_version_expiration { noncurrent_days = var.noncurrent_retention_days }
  }
  depends_on = [aws_s3_bucket_versioning.log_replica]
}
resource "aws_s3_bucket_notification" "replica" {
  provider    = aws.dr
  for_each    = local.kms_names
  bucket      = aws_s3_bucket.replica[each.key].id
  eventbridge = true
}
resource "aws_s3_bucket_notification" "log_replica" {
  provider    = aws.dr
  bucket      = aws_s3_bucket.log_replica.id
  eventbridge = true
}

# AWS server-access-log delivery requires a same-region SSE-S3 destination.
# Logging this sink to itself creates recursive traffic. Primary multi-region
# CloudTrail must audit reads of this terminal sink, as described in README.md.
#tfsec:ignore:aws-s3-enable-bucket-logging
#tfsec:ignore:aws-s3-encryption-customer-key
resource "aws_s3_bucket" "access_log_sink" {
  #checkov:skip=CKV_AWS_18:Terminal DR access-log sink must not log to itself; audit reads with the existing multi-region CloudTrail.
  #checkov:skip=CKV_AWS_145:AWS S3 server-access logging requires SSE-S3 on its destination, not SSE-KMS.
  #checkov:skip=CKV_AWS_144:Terminal DR log-delivery sink; another outbound DR region is not part of this one-way recovery architecture.
  provider = aws.dr
  bucket   = local.access_log_name
  tags     = merge(var.tags, { RecoveryRole = "terminal-access-delivery" })
}
resource "aws_s3_bucket_versioning" "access_log_sink" {
  provider = aws.dr
  bucket   = aws_s3_bucket.access_log_sink.id
  versioning_configuration { status = "Enabled" }
}
#tfsec:ignore:aws-s3-encryption-customer-key
resource "aws_s3_bucket_server_side_encryption_configuration" "access_log_sink" {
  provider = aws.dr
  bucket   = aws_s3_bucket.access_log_sink.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
resource "aws_s3_bucket_public_access_block" "access_log_sink" {
  provider                = aws.dr
  bucket                  = aws_s3_bucket.access_log_sink.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_ownership_controls" "access_log_sink" {
  provider = aws.dr
  bucket   = aws_s3_bucket.access_log_sink.id
  rule { object_ownership = "BucketOwnerEnforced" }
}
resource "aws_s3_bucket_policy" "access_log_sink" {
  provider = aws.dr
  bucket   = aws_s3_bucket.access_log_sink.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Sid = "TLSOnly", Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.access_log_sink.arn, "${aws_s3_bucket.access_log_sink.arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } },
    { Sid = "ScopedDelivery", Effect = "Allow", Principal = { Service = "logging.s3.amazonaws.com" }, Action = "s3:PutObject", Resource = "${aws_s3_bucket.access_log_sink.arn}/*", Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.dr.account_id }, ArnLike = { "aws:SourceArn" = [for bucket in local.destinations : bucket.arn] } } }
  ] })
}
resource "aws_s3_bucket_logging" "replica" {
  provider      = aws.dr
  for_each      = local.kms_names
  bucket        = aws_s3_bucket.replica[each.key].id
  target_bucket = aws_s3_bucket.access_log_sink.id
  target_prefix = "${each.key}/"
  depends_on    = [aws_s3_bucket_policy.access_log_sink]
}
resource "aws_s3_bucket_logging" "log_replica" {
  provider      = aws.dr
  bucket        = aws_s3_bucket.log_replica.id
  target_bucket = aws_s3_bucket.access_log_sink.id
  target_prefix = "access_logs/"
  depends_on    = [aws_s3_bucket_policy.access_log_sink]
}
resource "aws_s3_bucket_lifecycle_configuration" "access_log_sink" {
  provider = aws.dr
  bucket   = aws_s3_bucket.access_log_sink.id
  rule {
    id     = "audit-retention"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
    expiration { days = 365 }
    noncurrent_version_expiration { noncurrent_days = 365 }
  }
}
resource "aws_s3_bucket_notification" "access_log_sink" {
  provider    = aws.dr
  bucket      = aws_s3_bucket.access_log_sink.id
  eventbridge = true
}
resource "aws_iam_role_policy" "replication" {
  provider = aws.primary
  role     = aws_iam_role.replication.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Sid = "ReadSourceConfiguration", Effect = "Allow", Action = ["s3:GetReplicationConfiguration", "s3:ListBucket"], Resource = [for bucket in var.source_buckets : bucket.arn] },
    { Sid = "ReadSourceVersions", Effect = "Allow", Action = ["s3:GetObjectVersionForReplication", "s3:GetObjectVersionAcl", "s3:GetObjectVersionTagging"], Resource = [for bucket in var.source_buckets : "${bucket.arn}/*"] },
    { Sid = "WriteRecoveryReplicas", Effect = "Allow", Action = ["s3:ReplicateObject", "s3:ReplicateDelete", "s3:ReplicateTags"], Resource = [for bucket in local.destinations : "${bucket.arn}/*"] },
    { Sid = "DecryptActualSourceKeys", Effect = "Allow", Action = ["kms:Decrypt"], Resource = distinct([for source in local.kms_sources : source.kms_key_arn]), Condition = {
      StringEquals = { "kms:ViaService" = "s3.${data.aws_region.primary.name}.${data.aws_partition.current.dns_suffix}" },
      StringLike   = { "kms:EncryptionContext:aws:s3:arn" = flatten([for source in local.kms_sources : [source.arn, "${source.arn}/*"]]) }
    } },
    { Sid = "EncryptActualRecoveryKey", Effect = "Allow", Action = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey"], Resource = [aws_kms_key.replica.arn], Condition = {
      StringEquals = { "kms:ViaService" = "s3.${data.aws_region.dr.name}.${data.aws_partition.current.dns_suffix}" },
      StringLike   = { "kms:EncryptionContext:aws:s3:arn" = flatten([for name in keys(local.kms_sources) : [local.destinations[name].arn, "${local.destinations[name].arn}/*"]]) }
    } }
  ] })
}
