# ==============================================================================
# S3 Module — Model artifacts, evaluation reports, backups
# ==============================================================================

variable "name_prefix" { type = string }
variable "bucket_name" { type = string }
variable "tags"        { type = map(string) }

locals {
  bucket_name = var.bucket_name != "" ? var.bucket_name : "${var.name_prefix}-model-artifacts"
}

resource "aws_s3_bucket" "artifacts" {
  bucket = local.bucket_name
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "archive-old-artifacts"
    status = "Enabled"

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 365
      storage_class = "GLACIER"
    }

    noncurrent_version_expiration {
      noncurrent_days = 180
    }
  }
}

output "bucket_name" { value = aws_s3_bucket.artifacts.id }
output "bucket_arn"  { value = aws_s3_bucket.artifacts.arn }
