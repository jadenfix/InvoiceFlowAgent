# Five actual source rules. Recovery destinations and role permissions are separate.
resource "aws_s3_bucket_replication_configuration" "invoices_recovery" {
  bucket = module.s3.bucket_invoices
  role   = module.s3_replication.replication_role_arn
  rule {
    id       = "cross-region-recovery"
    priority = 1
    status   = "Enabled"
    filter {}
    delete_marker_replication { status = "Enabled" }
    source_selection_criteria {
      sse_kms_encrypted_objects { status = "Enabled" }
    }
    destination {
      bucket        = module.s3_replication.replica_buckets["invoices"].arn
      storage_class = "STANDARD"
      encryption_configuration {
        replica_kms_key_id = module.s3_replication.kms_key_arn
      }
    }
  }
  depends_on = [module.s3, module.s3_replication]
}

resource "aws_s3_bucket_replication_configuration" "processed_recovery" {
  bucket = module.s3.bucket_processed_invoices
  role   = module.s3_replication.replication_role_arn
  rule {
    id       = "cross-region-recovery"
    priority = 1
    status   = "Enabled"
    filter {}
    delete_marker_replication { status = "Enabled" }
    source_selection_criteria {
      sse_kms_encrypted_objects { status = "Enabled" }
    }
    destination {
      bucket        = module.s3_replication.replica_buckets["processed"].arn
      storage_class = "STANDARD"
      encryption_configuration {
        replica_kms_key_id = module.s3_replication.kms_key_arn
      }
    }
  }
  depends_on = [module.s3, module.s3_replication]
}

resource "aws_s3_bucket_replication_configuration" "logs_recovery" {
  bucket = module.s3.bucket_logs
  role   = module.s3_replication.replication_role_arn
  rule {
    id       = "cross-region-recovery"
    priority = 1
    status   = "Enabled"
    filter {}
    delete_marker_replication { status = "Enabled" }
    source_selection_criteria {
      sse_kms_encrypted_objects { status = "Enabled" }
    }
    destination {
      bucket        = module.s3_replication.replica_buckets["logs"].arn
      storage_class = "STANDARD"
      encryption_configuration {
        replica_kms_key_id = module.s3_replication.kms_key_arn
      }
    }
  }
  depends_on = [module.s3, module.s3_replication]
}

resource "aws_s3_bucket_replication_configuration" "backups_recovery" {
  bucket = module.s3.bucket_backups
  role   = module.s3_replication.replication_role_arn
  rule {
    id       = "cross-region-recovery"
    priority = 1
    status   = "Enabled"
    filter {}
    delete_marker_replication { status = "Enabled" }
    source_selection_criteria {
      sse_kms_encrypted_objects { status = "Enabled" }
    }
    destination {
      bucket        = module.s3_replication.replica_buckets["backups"].arn
      storage_class = "STANDARD"
      encryption_configuration {
        replica_kms_key_id = module.s3_replication.kms_key_arn
      }
    }
  }
  depends_on = [module.s3, module.s3_replication]
}

resource "aws_s3_bucket_replication_configuration" "access_logs_recovery" {
  bucket = module.s3.access_log_bucket_name
  role   = module.s3_replication.replication_role_arn
  rule {
    id       = "cross-region-recovery"
    priority = 1
    status   = "Enabled"
    filter {}
    delete_marker_replication { status = "Enabled" }
    destination {
      bucket        = module.s3_replication.replica_buckets["access_logs"].arn
      storage_class = "STANDARD"
    }
  }
  depends_on = [module.s3, module.s3_replication]
}
