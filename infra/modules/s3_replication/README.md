# Regional S3 recovery copies

This module creates the destinations and permissions for same-account, one-way
S3 cross-region replication of the five primary InvoiceFlow buckets. Each
environment has five explicit source replication rules in replication.tf. Pass genuine primary and recovery provider
aliases; the full plan rejects equal regions or different accounts. Source
versioning must already be enabled: callers depend on the complete primary S3
module before creating replication rules.

Four encrypted payload/log/backup sources opt into SSE-KMS replication and use a
new rotating key in the recovery region. The role reads only source versions,
writes only destination replicas, and uses the actual source/destination keys
through regional S3 endpoints with scoped encryption contexts. Bucket Keys are
disabled on recovery defaults; permissions also account for source bucket
contexts if those are enabled later. The role does not administer the keys.

The source server-access-log sink uses AWS-required SSE-S3. S3 replication
preserves the source encryption type, so its recovery copy is explicitly SSE-S3;
a destination default cannot turn those replicated objects into CMK ciphertext.
The separate recovery-region server-access-log sink also requires SSE-S3 and
receives logs from the five recovery buckets. It does not log itself. Both are
private, versioned, TLS-only, and have retention and EventBridge configuration.

The five primary sources receive real enabled rules at the environment root,
with direct source-bucket outputs and a dependency on the complete primary and
recovery modules. Recovery
buckets are terminal destinations, with no reverse replication, third region,
or replica-modification-sync loop. The only scanner exceptions concern these
specific terminal bucket roles: outbound CRR on recovery destinations; CMK
requirements on SSE-S3 access-log copies/delivery sinks; and self-logging on the
DR delivery sink. Other controls remain enabled. The primary multi-region
CloudTrail must audit reads of the two DR audit buckets. Add the deterministic
DR audit ARNs to its read-only selector without creating a module dependency
cycle; do not audit delivery writes back into a trail's own sink.

Replication is asynchronous. It does not automatically backfill old objects,
replicate lifecycle expiration, restore the application, or prove an RPO/RTO.
Delete markers are replicated, while older destination versions have independent
retention (365 days by default). Backfill requires a separately authorized S3
Batch Replication job. Before relying on recovery, use a real account to test an
encrypted upload, replication status, destination key/region, read permissions,
version recovery, failed-key behavior, and application restore.

Terraform fmt/init/schema checks and scanners are source evidence. No AWS plan
or apply has run without genuine account configuration. Applying this module
creates six additional S3 buckets, a regional KMS key and an IAM role; replication,
inter-region transfers, retained copies, logging and KMS requests incur normal
AWS costs. Backend protection, region selection, credentials and owner approval
are required before an apply.

Provider references:
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/setting-repl-config-perm-overview.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication-config-for-kms-objects.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/replication-what-is-isnot-replicated.html
- https://docs.aws.amazon.com/AmazonS3/latest/userguide/enable-server-access-logging.html
