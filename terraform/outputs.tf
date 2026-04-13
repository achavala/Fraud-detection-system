# ==============================================================================
# Root Outputs — Values needed for K8s deployment and CI/CD
# ==============================================================================

output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "eks_cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS API server endpoint"
  value       = module.eks.cluster_endpoint
}

output "ecr_repository_url" {
  description = "ECR repository URL for docker push"
  value       = module.ecr.repository_url
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint"
  value       = module.rds.endpoint
}

output "redis_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  value       = module.elasticache.primary_endpoint
}

output "secrets_manager_arn" {
  description = "AWS Secrets Manager ARN"
  value       = module.secrets.secret_arn
}

output "s3_model_bucket" {
  description = "S3 bucket for model artifacts"
  value       = module.s3.bucket_name
}

output "waf_acl_arn" {
  description = "WAF Web ACL ARN for ALB association"
  value       = module.waf.web_acl_arn
}

output "api_pod_role_arn" {
  description = "IAM role ARN for API pods (IRSA)"
  value       = module.iam.api_pod_role_arn
}

output "worker_pod_role_arn" {
  description = "IAM role ARN for Celery worker pods (IRSA)"
  value       = module.iam.worker_pod_role_arn
}

output "alb_controller_role_arn" {
  description = "IAM role ARN for ALB ingress controller"
  value       = module.iam.alb_controller_role_arn
}
