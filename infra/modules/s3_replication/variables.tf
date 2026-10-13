variable "project_name" {
  type = string
}
variable "environment" {
  type = string
}
variable "tags" {
  type    = map(string)
  default = {}
}
variable "source_buckets" {
  description = "Actual versioned source buckets; kms_encrypted is explicit so resource keys remain known before apply."
  type = map(object({
    id            = string
    arn           = string
    kms_encrypted = bool
    kms_key_arn   = optional(string)
  }))
  validation {
    condition     = length(var.source_buckets) == 5 && alltrue([for name in ["invoices", "processed", "logs", "backups", "access_logs"] : contains(keys(var.source_buckets), name)])
    error_message = "Provide all five named InvoiceFlow source buckets."
  }
  validation {
    condition     = alltrue([for source in var.source_buckets : source.kms_encrypted ? source.kms_key_arn != null : true])
    error_message = "KMS-encrypted sources require their actual regional key ARN."
  }
  validation {
    condition     = alltrue([for name in ["invoices", "processed", "logs", "backups"] : try(var.source_buckets[name].kms_encrypted, false)]) && !try(var.source_buckets["access_logs"].kms_encrypted, true)
    error_message = "The four application sources use actual customer keys; the access-log sink uses SSE-S3."
  }
}
variable "noncurrent_retention_days" {
  description = "Recovery copies retain older object versions independently of primary delete markers."
  type        = number
  default     = 365
  validation {
    condition     = var.noncurrent_retention_days >= 90
    error_message = "Retain recovery versions for at least 90 days."
  }
}

