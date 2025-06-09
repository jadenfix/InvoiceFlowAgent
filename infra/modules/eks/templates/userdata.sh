#!/bin/bash

# EKS Worker Node User Data Script
# This script initializes the worker node and joins it to the EKS cluster

set -e

# Bootstrap the node to the EKS cluster
/etc/eks/bootstrap.sh ${cluster_name} ${bootstrap_arguments}

# Install additional tools and configurations
yum update -y
yum install -y amazon-ssm-agent
systemctl enable amazon-ssm-agent
systemctl start amazon-ssm-agent

# Install CloudWatch agent
yum install -y amazon-cloudwatch-agent
systemctl enable amazon-cloudwatch-agent

# Configure log rotation
cat >> /etc/logrotate.d/kubernetes <<EOF
/var/log/pods/*/*.log {
    rotate 5
    daily
    compress
    missingok
    notifempty
    sharedscripts
}
EOF

# Set up node exporter for monitoring (if needed)
# This can be replaced with DaemonSet deployment
echo "Node initialization completed successfully" 