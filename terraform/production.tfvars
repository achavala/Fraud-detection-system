# ==============================================================================
# Production Environment — Terraform Variable Values
# ==============================================================================

project        = "fraud-detection"
environment    = "production"
aws_region     = "us-east-1"
aws_account_id = "REPLACE_WITH_YOUR_ACCOUNT_ID"

# Networking
vpc_cidr           = "10.0.0.0/16"
availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]

# EKS
eks_cluster_version     = "1.31"
eks_node_instance_types = ["m6i.xlarge", "m6i.2xlarge"]
eks_node_min_size       = 3
eks_node_max_size       = 20
eks_node_desired_size   = 5

# RDS PostgreSQL
rds_instance_class        = "db.r6g.xlarge"
rds_allocated_storage     = 100
rds_max_allocated_storage = 500
rds_multi_az              = true
rds_master_username       = "fraud_admin"
rds_database_name         = "fraud_db"

# ElastiCache Redis
redis_node_type          = "cache.r6g.large"
redis_num_cache_clusters = 3

# Domain
domain_name = "fraud-api.yourcompany.com"

tags = {
  Team        = "fraud-engineering"
  CostCenter  = "fraud-platform"
  Compliance  = "pci-dss"
}
