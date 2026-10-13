# Infrastructure validation and access design

CI uses Terraform 1.15.9. Terraform 1.6.0's embedded signing key rejected all current provider signatures; the maintained CLI installs the signed providers without disabling verification. Validation is `terraform init -backend=false -input=false` followed by `terraform validate`. No credentials, remote state, cloud plan, apply or destroy are required for this syntax/schema gate. `terraform fmt -check -recursive infra/` fails correctly on formatting errors.

## Access and audit defaults

Development/staging/production application security groups expose HTTPS only, but require `allowed_ingress_cidrs` supplied by the operator. This has no default and rejects unrestricted `0.0.0.0/0`. Supply the actual trusted client networks before planning. The ALB terminates TLS with the operator-supplied issued ACM certificate, forwards HTTPS to the actual gateway TLS NodePort, and registers managed EKS node ASGs dynamically. It does not serve a fake response or invent certificate/target identifiers. Deploy the application TLS gateway with `/health` and the declared NodePort before claiming application availability. No fake client CIDRs or certificate ARNs are provided.

EKS administration uses its private endpoint. Terraform/Kubernetes operators need network access inside the VPC (for example VPN or a VPC runner). Nodes require IMDSv2 and have private VPC/AWS endpoint egress, including the actual S3 gateway prefix list. Private STS, ECR, EC2/EKS, SSM and Logs endpoints support the AWS APIs used by the existing node roles. External model/ERP traffic needs an explicitly controlled egress path; unrestricted internet egress is not silently retained.

Public subnets retain their routes for managed networking, but do not autoassign public IPs to instances. VPC flow logs deliver to the encrypted audit bucket. RDS performance insights, Secrets Manager secrets, application/database CloudWatch logs, and CloudTrail use customer keys. Key policies restrict CloudWatch use by region/account/log context, and log delivery policies restrict writes to the correct account and source resources. CloudTrail is multi-region, validates logs and publishes to CloudWatch; source S3 buckets have versioning and server access logs.

## Resource-local scanner exceptions

The dedicated `aws_s3_bucket.access_log_sink` receives server access logs for the four source buckets. This sink has the following adjacent tfsec exceptions:

- `aws-s3-enable-bucket-logging` on the sink bucket. Logging the sink to itself creates recursive log traffic and cost; CloudTrail records its management changes and object reads instead. Delivery writes are excluded to prevent a second log-delivery feedback loop.
- `aws-s3-encryption-customer-key` on the sink's default encryption configuration. S3 server access log destinations must use SSE-S3 (AES256), not SSE-KMS. The source buckets retain their customer keys.

Official AWS references:

- [Enable server access logging](https://docs.aws.amazon.com/AmazonS3/latest/userguide/enable-server-access-logging.html).
- [Server access logging considerations and recursion](https://docs.aws.amazon.com/AmazonS3/latest/userguide/ServerLogs.html).
- [CloudTrail data-event delivery-loop warning](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html).
- [SSE-KMS restrictions for access-log destinations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingKMSEncryption.html).

The sink remains private with all four public-access blocks, TLS-only bucket policy, delivery restricted by source account and exact source bucket ARNs, versioning and 365-day retention. The CloudTrail bucket and source buckets have no scanner exceptions. The same SSE-S3 constraint is annotated for Checkov `CKV_AWS_145` on the sink.

The intentional public HTTPS ALB has tfsec `aws-elb-alb-not-public` (`AVD-AWS-0053`) annotated locally. Required trusted CIDRs, issued ACM certificate, TLS policy, WAF and private HTTPS targets remain enforced. AWS supports this public HTTPS design: https://docs.aws.amazon.com/elasticloadbalancing/latest/userguide/infrastructure-security.html.

The EKS-managed ASG attachment has Checkov `CKV2_AWS_15` annotated locally. EKS owns the ASG and node lifecycle/health; applying application ELB health to worker replacement conflates application and node failure. ALB target HTTPS health remains enabled; EC2/Kubernetes node health remains managed by EKS: https://docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html.

No global tfsec/Checkov exclusions or severity filters are introduced. Both CI security scanners now hard-fail applicable findings; the standalone workflow's inherited soft-fail settings are removed. Report a passing scan as **PASS with documented resource-role exceptions**, rather than unqualified zero findings.

## Scope of proof

Formatting, signed provider initialization, Terraform schema validation and security scans are infrastructure source checks. They do not prove AWS resource provisioning, network reachability, service availability, cost, or application deployment. Production now uses the same actual resource modules with its existing production sizing; source validation does not certify provisioning, an application rollout, or restore readiness. Cloud plans/applications require actual configured AWS identity, remote-state backend, trusted networks and review. No cloud plan/apply/destroy was performed during this repair.

## Source hardening and migration prerequisites

EKS defaults to supported Kubernetes 1.35 with EKS-managed AL2023 images and bootstrap. See https://docs.aws.amazon.com/eks/latest/userguide/kubernetes-versions.html. Existing clusters require an operator-reviewed staged version upgrade; this source change is not an in-place upgrade receipt.

Aurora manages the master secret and rotates it every seven days using a customer key, instead of retaining a plaintext generated password in Terraform state. Applications must retrieve the returned actual `secrets_manager_secret_arn`; existing secrets/password state requires reviewed migration. See https://docs.aws.amazon.com/AmazonRDS/latest/AuroraUserGuide/rds-secrets-manager.html. IAM database authentication is enabled in addition to the managed password. Daily AWS Backup copies, final snapshots, deletion protection and minor-version upgrades are enabled; restore ability is untested until configured AWS execution.

Supply actual stable `availability_zones`, `application_certificate_arn`, and `application_tls_node_port`, in addition to trusted CIDRs. WAF common protections and encrypted audit logs protect HTTPS ingress. Review the managed rules against application traffic before production rollout. ALB log delivery requires SSE-S3 too: https://docs.aws.amazon.com/elasticloadbalancing/latest/application/enable-access-logging.html.

Local Checkov checks run with `--skip-download --skip-results-upload --download-external-modules false` to keep the source scan local, without changing the set of applicable rules.

## Cloud-plan readiness

The workflow reports `AWS plan NOT_EXECUTED` and skips the plan when no actual `AWS_ROLE_ARN` is configured. It outputs only a presence boolean, never the identity secret. With a real role, the plan uses `-input=false` and requires real remote state and deployment inputs; missing inputs remain a failure rather than a fabricated plan. Existing apply conditions are unchanged. This source repair performs no apply or destroy.

## Review before any future apply

The declared architecture is billable: one EKS control plane per environment; managed EC2 node groups at the existing environment capacities; NAT gateways and private interface endpoint ENIs per selected AZ; Aurora instances, storage and retained snapshots; customer KMS keys; an HTTPS ALB and managed WAF rules; CloudWatch/S3 logs; daily AWS Backup recovery copies; and cross-region object replicas/transfer. Production retains its larger existing node/RDS sizing. Review quantities, retention, restore objectives and account budgets before any apply. No resources were created and no cloud provisioning cost was incurred by this source validation work.

An issued hostname certificate and a deployed TLS application gateway/NodePort with a working `/health` endpoint are real external workload prerequisites. DNS, chart rollout, IAM/application secret integration and actual cloud end-to-end reachability remain unverified; a green source scan is not an application deployment receipt. The current locally persisted PDF/RabbitMQ/PostgreSQL/browser workflow has its separate real-stack CI proof.

## One-way regional object recovery

All five primary S3 buckets have enabled cross-region replication into actual, versioned same-account recovery buckets. A required `dr_region` selects the recovery provider; the module rejects equal regions/accounts. Four customer-key encrypted sources use scoped key permissions; the required SSE-S3 access-log source retains that encryption type. Recovery replicas are terminal destinations, avoiding reverse replication loops. The primary multi-region CloudTrail audits DR audit-bucket reads using actual object prefix ARNs (`/`, not IAM `/*` patterns). See [the recovery module's exact exceptions and restore scope](modules/s3_replication/README.md).

The recovery module has further resource-local exceptions for terminal replicas' outbound CRR and required SSE-S3/self-logging restrictions on its audit buckets. No source replication rule is skipped. Replication is asynchronous and does not backfill existing objects or prove application recovery; actual upload/key/failure/restore tests remain unexecuted without configured AWS identity. See https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication-what-is-isnot-replicated.html and https://docs.aws.amazon.com/awscloudtrail/latest/APIReference/API_DataResource.html.

Aurora defaults remain on PostgreSQL major 15 and use the published 15.18 maintenance release, with automatic minor upgrades enabled: https://aws.amazon.com/about-aws/whats-new/2026/08/amazon-aurora-postgresql-18-4-17-10-16-14-15-18-14-23/. Confirm actual regional engine/instance availability and reviewed upgrade paths with the configured account before planning.
