# InvoiceFlow Agent Deployment Guide

This guide will walk you through deploying the InvoiceFlow Agent infrastructure from scratch.

## Prerequisites

Before you begin, ensure you have the following tools installed and configured:

- **AWS CLI** (configured with appropriate permissions)
- **Terraform** >= 1.5.0
- **Docker**
- **kubectl**
- **Helm**
- **Git**

## AWS Permissions Required

Your AWS user/role needs the following permissions:

- Full access to VPC, EC2, EKS, RDS, S3, IAM
- CloudWatch, CloudTrail, and KMS management
- Secrets Manager and Systems Manager access

## Step 1: Clone and Initialize

```bash
# Clone the repository
git clone https://github.com/jadenfix/InvoiceFlowAgent.git
cd InvoiceFlowAgent

# Verify AWS CLI configuration
aws sts get-caller-identity
```

## Step 2: Set Up Terraform Backend

Before deploying any environment, you need to set up the Terraform backend:

```bash
# Navigate to the scripts directory
cd infra/scripts

# Make the script executable (if not already)
chmod +x setup-backend.sh

# Set up backends for all environments
./setup-backend.sh dev staging prod

# Or set up just the dev environment
./setup-backend.sh dev
```

This script will:
- Create S3 buckets for Terraform state storage
- Create DynamoDB tables for state locking
- Configure proper encryption and security settings
- Generate backend configuration files

## Step 3: Deploy Development Environment

```bash
# Navigate to the dev environment
cd ../environments/dev

# Initialize Terraform
terraform init

# Review the plan
terraform plan

# Apply the infrastructure
terraform apply
```

The deployment will take approximately 15-20 minutes and will create:
- VPC with public and private subnets
- EKS cluster with managed node groups
- RDS Aurora PostgreSQL cluster
- S3 buckets for storage
- Security groups and networking
- CloudWatch log groups

## Step 4: Configure kubectl

After the EKS cluster is deployed, configure kubectl:

```bash
# Get the configuration command from Terraform output
terraform output configure_kubectl

# Run the command (example)
aws eks update-kubeconfig --region us-west-2 --name invoiceflow-dev-cluster

# Verify connectivity
kubectl get nodes
```

## Step 5: Deploy Staging Environment (Optional)

```bash
# Navigate to staging environment
cd ../staging

# Initialize and deploy
terraform init
terraform plan
terraform apply
```

## Step 6: Deploy Production Environment (Optional)

```bash
# Navigate to production environment
cd ../prod

# Initialize and deploy
terraform init
terraform plan
terraform apply
```

## Infrastructure Outputs

After deployment, you can retrieve important information:

```bash
# Get all outputs
terraform output

# Get specific outputs
terraform output cluster_endpoint
terraform output rds_cluster_endpoint
terraform output s3_bucket_invoices
```

## Verifying the Deployment

### 1. Check EKS Cluster

```bash
# List nodes
kubectl get nodes

# Check system pods
kubectl get pods -n kube-system

# Check node groups
aws eks describe-nodegroup --cluster-name invoiceflow-dev-cluster --nodegroup-name general
```

### 2. Check RDS Cluster

```bash
# List RDS clusters
aws rds describe-db-clusters --query 'DBClusters[?DBClusterIdentifier==`invoiceflow-dev-cluster`]'

# Check cluster status
aws rds describe-db-clusters --db-cluster-identifier invoiceflow-dev-cluster --query 'DBClusters[0].Status'
```

### 3. Check S3 Buckets

```bash
# List buckets
aws s3 ls | grep invoiceflow

# Check bucket policies
aws s3api get-bucket-encryption --bucket invoiceflow-dev-invoices-ACCOUNT_ID
```

## Common Issues and Troubleshooting

### Issue: Terraform Backend Not Found

**Problem**: Error initializing backend
**Solution**: Run the backend setup script first

```bash
cd infra/scripts
./setup-backend.sh dev
```

### Issue: EKS Node Groups Not Ready

**Problem**: Node groups stuck in creating state
**Solution**: Check IAM permissions and subnet configuration

```bash
# Check node group status
aws eks describe-nodegroup --cluster-name CLUSTER_NAME --nodegroup-name NODE_GROUP_NAME

# Check CloudTrail for errors
aws logs filter-log-events --log-group-name /aws/eks/CLUSTER_NAME/cluster
```

### Issue: RDS Connection Timeout

**Problem**: Cannot connect to RDS from EKS
**Solution**: Check security groups and network ACLs

```bash
# Test connectivity from a pod
kubectl run test-pod --image=alpine --rm -it -- sh
# Inside the pod:
# apk add postgresql-client
# psql -h RDS_ENDPOINT -U USERNAME -d DATABASE_NAME
```

### Issue: S3 Access Denied

**Problem**: Applications cannot access S3 buckets
**Solution**: Check IAM roles and policies

```bash
# Check bucket policy
aws s3api get-bucket-policy --bucket BUCKET_NAME

# Test access
aws s3 ls s3://BUCKET_NAME
```

## Environment-Specific Configurations

### Development
- Minimal resources for cost optimization
- Single AZ for some components
- Shorter log retention periods
- Less stringent security (for development ease)

### Staging
- Production-like configuration
- Multi-AZ setup
- Longer retention periods
- Production security settings

### Production
- High availability across multiple AZs
- Large instance sizes
- Maximum retention periods
- Strict security and monitoring
- Cross-region backups enabled

## Cost Optimization

### Development Environment
- Use Spot instances where possible
- Smaller RDS instances (db.t3.micro)
- Shorter log retention (30 days)
- Single AZ deployments

### Production Environment
- Use Reserved Instances for predictable workloads
- Enable S3 lifecycle policies
- Use appropriate storage classes
- Monitor unused resources

## Security Best Practices

1. **Network Security**
   - Private subnets for databases and applications
   - Security groups with minimal required access
   - VPC endpoints for AWS services

2. **Data Security**
   - Encryption at rest for all storage
   - Encryption in transit
   - Regular key rotation

3. **Access Control**
   - IAM roles with least privilege
   - No hardcoded credentials
   - Regular access reviews

4. **Monitoring**
   - CloudTrail for audit logging
   - CloudWatch for monitoring
   - Security Hub for compliance

## Backup and Disaster Recovery

### Automated Backups
- RDS automated backups (7-30 days)
- S3 versioning enabled
- Cross-region replication for production

### Manual Backups
```bash
# Create RDS snapshot
aws rds create-db-cluster-snapshot \
  --db-cluster-snapshot-identifier manual-snapshot-$(date +%Y%m%d) \
  --db-cluster-identifier invoiceflow-prod-cluster

# Backup S3 bucket
aws s3 sync s3://source-bucket s3://backup-bucket --delete
```

## Monitoring and Alerting

### CloudWatch Dashboards
- Infrastructure metrics
- Application metrics
- Cost tracking

### Alerts
- EKS node health
- RDS connection issues
- S3 access errors
- Cost anomalies

## Cleanup

To destroy the infrastructure:

```bash
# WARNING: This will delete all resources
terraform destroy

# Clean up backend resources (optional)
aws s3 rb s3://invoiceflow-terraform-state-dev-ACCOUNT_ID --force
aws dynamodb delete-table --table-name invoiceflow-terraform-locks-dev
```

## Next Steps

After the infrastructure is deployed:

1. **Deploy Applications**: Use the Helm charts in the `charts/` directory
2. **Configure CI/CD**: Set up GitHub Actions secrets for automated deployments
3. **Set up Monitoring**: Deploy Prometheus, Grafana, and alerting
4. **Security Scanning**: Implement container and dependency scanning
5. **Backup Testing**: Verify backup and restore procedures

## Support

For issues or questions:
- Check the [troubleshooting section](#common-issues-and-troubleshooting)
- Review [GitHub Issues](https://github.com/jadenfix/InvoiceFlowAgent/issues)
- Consult the [Contributing Guide](../CONTRIBUTING.md)

## Additional Resources

- [AWS EKS Documentation](https://docs.aws.amazon.com/eks/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [Kubernetes Documentation](https://kubernetes.io/docs/) 