# ==============================================================================
# Secrets Manager Module — Centralized secret storage
# ==============================================================================

variable "name_prefix"         { type = string }
variable "rds_endpoint"        { type = string }
variable "rds_port"            { type = number }
variable "rds_master_username" { type = string }
variable "rds_master_password" { type = string sensitive = true }
variable "rds_database_name"   { type = string }
variable "redis_endpoint"      { type = string }
variable "redis_port"          { type = number }
variable "tags"                { type = map(string) }

resource "random_password" "secret_key" {
  length  = 64
  special = true
}

locals {
  rds_host = split(":", var.rds_endpoint)[0]
  secret_value = {
    SECRET_KEY       = random_password.secret_key.result
    DATABASE_URL     = "postgresql+asyncpg://${var.rds_master_username}:${var.rds_master_password}@${local.rds_host}:${var.rds_port}/${var.rds_database_name}"
    DATABASE_URL_SYNC = "postgresql://${var.rds_master_username}:${var.rds_master_password}@${local.rds_host}:${var.rds_port}/${var.rds_database_name}"
    REDIS_URL        = "rediss://${var.redis_endpoint}:${var.redis_port}/0"
    CELERY_BROKER_URL = "rediss://${var.redis_endpoint}:${var.redis_port}/0"
    OPENAI_API_KEY   = "REPLACE_ME"
    ANTHROPIC_API_KEY = "REPLACE_ME"
    SLACK_BOT_TOKEN  = "REPLACE_ME"
    GITHUB_TOKEN     = "REPLACE_ME"
  }
}

resource "aws_secretsmanager_secret" "platform" {
  name                    = "${var.name_prefix}/platform-secrets"
  description             = "Fraud Detection Platform — all application secrets"
  recovery_window_in_days = 30
  tags                    = var.tags
}

resource "aws_secretsmanager_secret_version" "platform" {
  secret_id     = aws_secretsmanager_secret.platform.id
  secret_string = jsonencode(local.secret_value)
}

output "secret_arn"  { value = aws_secretsmanager_secret.platform.arn }
output "secret_name" { value = aws_secretsmanager_secret.platform.name }
