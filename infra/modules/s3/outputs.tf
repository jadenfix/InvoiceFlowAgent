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