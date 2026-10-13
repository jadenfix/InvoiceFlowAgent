# Infrastructure validation and access design

CI uses Terraform 1.15.9. Terraform 1.6.0's embedded signing key rejected all current provider signatures; the maintained CLI installs the signed providers without disabling verification. Validation is `terraform init -backend=false -input=false` followed by `terraform validate`. No credentials, remote state, cloud plan, apply or destroy are required for this syntax/schema gate. `terraform fmt -check -recursive infra/` fails correctly on formatting errors.

## Access and audit defaults

Development/staging application security groups keep HTTP redirect and HTTPS ports, but require `allowed_ingress_cidrs` supplied by the operator. This has no default and rejects unrestricted `0.0.0.0/0`. Supply the actual trusted client networks before planning. This configuration does not create a TLS listener/certificate; the application's ingress deployment must provide its real certificate and listener configuration. No fake client CIDRs or certificate ARNs are provided.

EKS administration uses its private endpoint. Terraform/Kubernetes operators need network access inside the VPC (for example VPN or a VPC runner). Nodes require IMDSv2 and have private VPC/AWS endpoint egress, including the actual S3 gateway prefix list. Private STS, ECR, EC2/EKS, SSM and Logs endpoints support the AWS APIs used by the existing node roles. External model/ERP traffic needs an explicitly controlled egress path; unrestricted internet egress is not silently retained.

Public subnets retain their routes for managed networking, but do not autoassign public IPs to instances. VPC flow logs deliver to the encrypted audit bucket. RDS performance insights, Secrets Manager secrets, application/database CloudWatch logs, and CloudTrail use customer keys. Key policies restrict CloudWatch use by region/account/log context, and log delivery policies restrict writes to the correct account and source resources. CloudTrail is multi-region, validates logs and publishes to CloudWatch; source S3 buckets have versioning and server access logs.

## Two resource-local scanner exceptions

The dedicated `aws_s3_bucket.access_log_sink` receives server access logs for the four source buckets. Only this sink has the following adjacent tfsec exceptions:

- `aws-s3-enable-bucket-logging` on the sink bucket. Logging the sink to itself creates recursive log traffic and cost; CloudTrail records its management changes and object reads instead. Delivery writes are excluded to prevent a second log-delivery feedback loop.
- `aws-s3-encryption-customer-key` on the sink's default encryption configuration. S3 server access log destinations must use SSE-S3 (AES256), not SSE-KMS. The source buckets retain their customer keys.

Official AWS references:

- [Enable server access logging](https://docs.aws.amazon.com/AmazonS3/latest/userguide/enable-server-access-logging.html).
- [Server access logging considerations and recursion](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ServerLogs.html).
- [CloudTrail data-event delivery-loop warning](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html).
- [SSE-KMS restrictions for access-log destinations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingKMSEncryption.html).

The sink remains private with all four public-access blocks, TLS-only bucket policy, delivery restricted by source account and exact source bucket ARNs, versioning and 365-day retention. The CloudTrail bucket and source buckets have no scanner exceptions. No global tfsec exclusions, severity filters or soft-fail changes are introduced. Report a passing scan as **PASS with these documented log-sink exceptions**, rather than unqualified zero findings.

## Scope of proof

Formatting, signed provider initialization, Terraform schema validation and security scans are infrastructure source checks. They do not prove AWS resource provisioning, network reachability, service availability, cost, or application deployment. Production currently contains variables only, as in the original repository; a successful validation of those variables does not certify a complete production stack. Cloud plans/applications require actual configured AWS identity, remote-state backend, trusted networks and review. No cloud plan/apply/destroy was performed during this repair.
