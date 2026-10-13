output "bucket_invoices" {
  description = "Name of the S3 bucket for raw invoices"
  value       = aws_s3_bucket.invoices.id
}

output "bucket_invoices_arn" {
  description = "ARN of the S3 bucket for raw invoices"
  value       = aws_s3_bucket.invoices.arn
}

output "bucket_processed_invoices" {
  description = "Name of the S3 bucket for processed invoices"
  value       = aws_s3_bucket.processed_invoices.id
}

output "bucket_processed_invoices_arn" {
  description = "ARN of the S3 bucket for processed invoices"
  value       = aws_s3_bucket.processed_invoices.arn
}

output "bucket_logs" {
  description = "Name of the S3 bucket for logs"
  value       = aws_s3_bucket.logs.id
}

output "bucket_logs_arn" {
  description = "ARN of the S3 bucket for logs"
  value       = aws_s3_bucket.logs.arn
}

output "bucket_backups" {
  description = "Name of the S3 bucket for backups"
  value       = aws_s3_bucket.backups.id
}

output "bucket_backups_arn" {
  description = "ARN of the S3 bucket for backups"
  value       = aws_s3_bucket.backups.arn
}

output "kms_key_arn" {
  description = "ARN of the KMS key used for S3 encryption"
  value       = aws_kms_key.s3.arn
}

output "kms_key_id" {
  description = "ID of the KMS key used for S3 encryption"
  value       = aws_kms_key.s3.key_id
}

output "cloudtrail_arn" {
  description = "ARN of the CloudTrail for S3 access logging"
  value       = aws_cloudtrail.s3_access.arn
}
output "flow_log_destination" { value = "${aws_s3_bucket.logs.arn}/vpc-flow/" }

output "access_log_bucket_name" { value = aws_s3_bucket.access_log_sink.bucket }

output "replication_sources" {
  value = {
    invoices    = { id = aws_s3_bucket.invoices.id, arn = aws_s3_bucket.invoices.arn, kms_encrypted = true, kms_key_arn = aws_kms_key.s3.arn }
    processed   = { id = aws_s3_bucket.processed_invoices.id, arn = aws_s3_bucket.processed_invoices.arn, kms_encrypted = true, kms_key_arn = aws_kms_key.s3.arn }
    logs        = { id = aws_s3_bucket.logs.id, arn = aws_s3_bucket.logs.arn, kms_encrypted = true, kms_key_arn = aws_kms_key.s3.arn }
    backups     = { id = aws_s3_bucket.backups.id, arn = aws_s3_bucket.backups.arn, kms_encrypted = true, kms_key_arn = aws_kms_key.s3.arn }
    access_logs = { id = aws_s3_bucket.access_log_sink.id, arn = aws_s3_bucket.access_log_sink.arn, kms_encrypted = false, kms_key_arn = null }
  }
}
