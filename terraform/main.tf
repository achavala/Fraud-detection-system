# ==============================================================================
# Fraud Detection Platform — Root Terraform Configuration
# Enterprise AWS Architecture: EKS + RDS + ElastiCache + S3 + WAF
# ==============================================================================

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.27"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.12"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  backend "s3" {
    bucket         = "fraud-detection-terraform-state"
    key            = "infrastructure/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "fraud-detection-terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = merge(var.tags, {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    })
  }
}

provider "kubernetes" {
  host                   = module.eks.cluster_endpoint
  cluster_ca_certificate = base64decode(module.eks.cluster_ca_certificate)
  exec {
    api_version = "client.authentication.k8s.io/v1beta1"
    command     = "aws"
    args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
  }
}

provider "helm" {
  kubernetes {
    host                   = module.eks.cluster_endpoint
    cluster_ca_certificate = base64decode(module.eks.cluster_ca_certificate)
    exec {
      api_version = "client.authentication.k8s.io/v1beta1"
      command     = "aws"
      args        = ["eks", "get-token", "--cluster-name", module.eks.cluster_name]
    }
  }
}

locals {
  name_prefix = "${var.project}-${var.environment}"

  common_tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# ==============================================================================
# 1. NETWORKING — VPC with public/private/data subnets across 3 AZs
# ==============================================================================

module "vpc" {
  source = "./modules/vpc"

  name_prefix        = local.name_prefix
  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  tags               = local.common_tags
}

# ==============================================================================
# 2. EKS CLUSTER — Managed Kubernetes with IRSA
# ==============================================================================

module "eks" {
  source = "./modules/eks"

  name_prefix         = local.name_prefix
  cluster_version     = var.eks_cluster_version
  vpc_id              = module.vpc.vpc_id
  private_subnet_ids  = module.vpc.private_subnet_ids
  node_instance_types = var.eks_node_instance_types
  node_min_size       = var.eks_node_min_size
  node_max_size       = var.eks_node_max_size
  node_desired_size   = var.eks_node_desired_size
  tags                = local.common_tags
}

# ==============================================================================
# 3. RDS POSTGRESQL 16 — Multi-AZ, encrypted, automated backups
# ==============================================================================

module "rds" {
  source = "./modules/rds"

  name_prefix           = local.name_prefix
  vpc_id                = module.vpc.vpc_id
  database_subnet_ids   = module.vpc.database_subnet_ids
  eks_security_group_id = module.eks.node_security_group_id
  instance_class        = var.rds_instance_class
  allocated_storage     = var.rds_allocated_storage
  max_allocated_storage = var.rds_max_allocated_storage
  multi_az              = var.rds_multi_az
  master_username       = var.rds_master_username
  database_name         = var.rds_database_name
  tags                  = local.common_tags
}

# ==============================================================================
# 4. ELASTICACHE REDIS — Replication group with encryption
# ==============================================================================

module "elasticache" {
  source = "./modules/elasticache"

  name_prefix           = local.name_prefix
  vpc_id                = module.vpc.vpc_id
  database_subnet_ids   = module.vpc.database_subnet_ids
  eks_security_group_id = module.eks.node_security_group_id
  node_type             = var.redis_node_type
  num_cache_clusters    = var.redis_num_cache_clusters
  tags                  = local.common_tags
}

# ==============================================================================
# 5. ECR — Container image registry
# ==============================================================================

module "ecr" {
  source = "./modules/ecr"

  name_prefix = local.name_prefix
  tags        = local.common_tags
}

# ==============================================================================
# 6. S3 — Model artifacts, evaluation reports, backups
# ==============================================================================

module "s3" {
  source = "./modules/s3"

  name_prefix = local.name_prefix
  bucket_name = var.model_artifacts_bucket_name
  tags        = local.common_tags
}

# ==============================================================================
# 7. SECRETS MANAGER — All sensitive configuration
# ==============================================================================

module "secrets" {
  source = "./modules/secrets"

  name_prefix          = local.name_prefix
  rds_endpoint         = module.rds.endpoint
  rds_port             = module.rds.port
  rds_master_username  = var.rds_master_username
  rds_master_password  = module.rds.master_password
  rds_database_name    = var.rds_database_name
  redis_endpoint       = module.elasticache.primary_endpoint
  redis_port           = module.elasticache.port
  tags                 = local.common_tags
}

# ==============================================================================
# 8. IAM — IRSA roles for pod-level AWS access
# ==============================================================================

module "iam" {
  source = "./modules/iam"

  name_prefix            = local.name_prefix
  eks_oidc_provider_arn  = module.eks.oidc_provider_arn
  eks_oidc_provider_url  = module.eks.oidc_provider_url
  secrets_arn            = module.secrets.secret_arn
  s3_bucket_arn          = module.s3.bucket_arn
  ecr_repository_arn     = module.ecr.repository_arn
  tags                   = local.common_tags
}

# ==============================================================================
# 9. WAF — Web Application Firewall for API protection
# ==============================================================================

module "waf" {
  source = "./modules/waf"

  name_prefix = local.name_prefix
  tags        = local.common_tags
}
