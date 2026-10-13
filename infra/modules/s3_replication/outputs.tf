output "replica_buckets" {
  description = "Actual recovery destination names and ARNs; no availability or restore claim."
  value       = { for name, bucket in local.destinations : name => { id = bucket.id, arn = bucket.arn } }
}
output "kms_key_arn" { value = aws_kms_key.replica.arn }
output "replication_role_arn" {
  value      = aws_iam_role.replication.arn
  depends_on = [aws_iam_role_policy.replication]
}
output "access_log_sink_arn" { value = aws_s3_bucket.access_log_sink.arn }
output "readonly_audit_object_prefixes" {
  description = "Wire these to the primary multi-region CloudTrail data selectors, avoiding log delivery write recursion."
  value       = concat(["${aws_s3_bucket.access_log_sink.arn}/"], ["${aws_s3_bucket.log_replica.arn}/"])
}
