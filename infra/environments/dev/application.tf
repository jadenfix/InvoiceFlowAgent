# HTTPS ingress for the actual deployed TLS gateway, not a placeholder response.
# Public HTTPS is intentional: required trusted CIDRs, real ACM certificate,
# TLS1.3-capable policy, WAF and private HTTPS targets retain layered controls.
# https://docs.aws.amazon.com/elasticloadbalancing/latest/userguide/infrastructure-security.html
#tfsec:ignore:aws-elb-alb-not-public
resource "aws_lb" "application" {
  name                       = "${var.project_name}-${var.environment}-app"
  internal                   = false
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.application_load_balancer.id]
  subnets                    = module.vpc.public_subnet_ids
  enable_deletion_protection = true
  drop_invalid_header_fields = true
  access_logs {
    bucket  = module.s3.access_log_bucket_name
    prefix  = "alb"
    enabled = true
  }
  tags       = local.common_tags
  depends_on = [module.s3]
}
resource "aws_lb_target_group" "application" {
  name        = "${var.project_name}-${var.environment}-app"
  port        = var.application_tls_node_port
  protocol    = "HTTPS"
  vpc_id      = module.vpc.vpc_id
  target_type = "instance"
  health_check {
    protocol = "HTTPS"
    path     = "/health"
    matcher  = "200"
  }
  tags = local.common_tags
}
resource "aws_lb_listener" "application" {
  load_balancer_arn = aws_lb.application.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.application_certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.application.arn
  }
}
# EKS owns the ASG lifecycle and EC2/Kubernetes node health. Application TLS
# health must remove targets, not replace a healthy Kubernetes worker.
# https://docs.aws.amazon.com/eks/latest/userguide/managed-node-groups.html
resource "aws_autoscaling_attachment" "application" {
  #checkov:skip=CKV2_AWS_15:EKS-managed ASG uses node health; ALB HTTPS target health is configured separately.
  for_each               = module.eks.node_autoscaling_groups
  autoscaling_group_name = each.value
  lb_target_group_arn    = aws_lb_target_group.application.arn
}
resource "aws_security_group_rule" "application_gateway" {
  type                     = "ingress"
  description              = "TLS gateway NodePort from application ALB only"
  security_group_id        = module.eks.node_security_group_id
  source_security_group_id = aws_security_group.application_load_balancer.id
  from_port                = var.application_tls_node_port
  to_port                  = var.application_tls_node_port
  protocol                 = "tcp"
}
resource "aws_wafv2_web_acl" "application" {
  name  = "${var.project_name}-${var.environment}-application"
  scope = "REGIONAL"
  default_action {
    allow {}
  }
  rule {
    name     = "AWSCommonProtection"
    priority = 1
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesCommonRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-${var.environment}-common"
      sampled_requests_enabled   = true
    }
  }
  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 2
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-${var.environment}-2"
      sampled_requests_enabled   = true
    }
  }
  rule {
    name     = "AWSManagedRulesAnonymousIpList"
    priority = 3
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        name        = "AWSManagedRulesAnonymousIpList"
        vendor_name = "AWS"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "${var.project_name}-${var.environment}-3"
      sampled_requests_enabled   = true
    }
  }
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "${var.project_name}-${var.environment}-application"
    sampled_requests_enabled   = true
  }
  tags = local.common_tags
}
resource "aws_wafv2_web_acl_association" "application" {
  resource_arn = aws_lb.application.arn
  web_acl_arn  = aws_wafv2_web_acl.application.arn
}
module "waf_log_key" {
  source           = "../../modules/cloudwatch_key"
  name             = "${var.project_name}-${var.environment}-waf"
  log_group_prefix = "aws-waf-logs-${var.project_name}-${var.environment}"
  tags             = local.common_tags
}
resource "aws_cloudwatch_log_group" "waf" {
  name              = "aws-waf-logs-${var.project_name}-${var.environment}"
  retention_in_days = 365
  kms_key_id        = module.waf_log_key.arn
  tags              = local.common_tags
}
resource "aws_wafv2_web_acl_logging_configuration" "application" {
  log_destination_configs = [aws_cloudwatch_log_group.waf.arn]
  resource_arn            = aws_wafv2_web_acl.application.arn
}
output "application_hostname" { value = aws_lb.application.dns_name }
