# ==============================================================================
# Fraud Detection Platform — Terraform Variables
# Enterprise-grade AWS EKS deployment
# ==============================================================================

variable "project" {
  description = "Project name used for resource naming and tagging"
  type        = string
  default     = "fraud-detection"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"
  validation {
    condition     = contains(["production", "staging", "development"], var.environment)
    error_message = "Environment must be production, staging, or development."
  }
}

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "us-east-1"
}

variable "aws_account_id" {
  description = "AWS account ID"
  type        = string
}

# --- Networking ---

variable "vpc_cidr" {
  description = "VPC CIDR block"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "AZs for multi-AZ deployment"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

# --- EKS ---

variable "eks_cluster_version" {
  description = "Kubernetes version for EKS"
  type        = string
  default     = "1.31"
}

variable "eks_node_instance_types" {
  description = "EC2 instance types for EKS managed node group"
  type        = list(string)
  default     = ["m6i.xlarge", "m6i.2xlarge"]
}

variable "eks_node_min_size" {
  type    = number
  default = 3
}

variable "eks_node_max_size" {
  type    = number
  default = 20
}

variable "eks_node_desired_size" {
  type    = number
  default = 5
}

# --- RDS (PostgreSQL) ---

variable "rds_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.r6g.xlarge"
}

variable "rds_allocated_storage" {
  type    = number
  default = 100
}

variable "rds_max_allocated_storage" {
  type    = number
  default = 500
}

variable "rds_multi_az" {
  type    = bool
  default = true
}

variable "rds_master_username" {
  type    = string
  default = "fraud_admin"
}

variable "rds_database_name" {
  type    = string
  default = "fraud_db"
}

# --- ElastiCache (Redis) ---

variable "redis_node_type" {
  type    = string
  default = "cache.r6g.large"
}

variable "redis_num_cache_clusters" {
  description = "Number of Redis replicas (1 primary + N-1 read replicas)"
  type        = number
  default     = 3
}

# --- S3 ---

variable "model_artifacts_bucket_name" {
  type    = string
  default = ""
}

# --- Domain ---

variable "domain_name" {
  description = "Domain for the fraud API (e.g., fraud-api.yourcompany.com)"
  type        = string
  default     = ""
}

variable "tags" {
  description = "Common tags for all resources"
  type        = map(string)
  default     = {}
}
