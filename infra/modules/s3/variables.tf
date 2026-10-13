variable "project_name" {
  description = "Name of the project"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "tags" {
  description = "A map of tags to assign to the resource"
  type        = map(string)
  default     = {}
}
variable "extra_audit_bucket_arns" {
  description = "Actual additional log-object prefix ARNs audited for reads only; prevents delivery-event loops"
  type        = list(string)
  default     = []
}
