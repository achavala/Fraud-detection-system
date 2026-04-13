# Fraud Detection Platform — Enterprise AWS Architecture

## Architecture Overview

```
                                   Internet
                                      |
                              +-------+-------+
                              |   Route 53    |
                              | (DNS + Health)|
                              +-------+-------+
                                      |
                              +-------+-------+
                              |   AWS WAF     |
                              | (Rate Limit,  |
                              |  SQLi, XSS,   |
                              |  Geo-Block)   |
                              +-------+-------+
                                      |
                              +-------+-------+
                              |     ALB       |
                              | (TLS 1.3,     |
                              |  ACM Cert)    |
                              +-------+-------+
                                      |
                    +-----------------+-----------------+
                    |           VPC 10.0.0.0/16         |
                    |                                   |
   +----------------+--+  +---+---+  +-----------+     |
   | Public Subnets    |  |Private|  |Data Subnet|     |
   | 10.0.0.0/20 x3   |  |Subnets|  |10.0.128+  |     |
   | (ALB, NAT GW)    |  |10.0.64|  |(RDS,Redis)|     |
   +-------------------+  +---+---+  +-----+-----+     |
                               |            |           |
                    +----------+----------+ |           |
                    |    EKS Cluster       | |           |
                    |  +----------------+ | |           |
                    |  | fraud-api (3+) | | |           |
                    |  | HPA: 3→30     +---+----→ RDS PostgreSQL 16
                    |  | PDB: min 2    | | |    | Multi-AZ, encrypted
                    |  +----------------+ | |    | r6g.xlarge
                    |  +----------------+ | |    | 35-day backups
                    |  | celery-worker  | | |    +------------------
                    |  | HPA: 3→15    +---+----→ ElastiCache Redis 7
                    |  +----------------+ | |    | 3-node repl group
                    |  +----------------+ | |    | TLS in-transit
                    |  | celery-beat    | | |    +------------------
                    |  | (singleton)    | | |
                    |  +----------------+ | |
                    |  +----------------+ | |
                    |  | qdrant (STS)   | | |
                    |  | gp3 EBS 50Gi  | | |
                    |  +----------------+ | |
                    +---------------------+ |
                    +-----------------+-----+--------+
```

## Component Mapping: Local → AWS

| Local (Docker Compose) | AWS Production | Why |
|---|---|---|
| `postgres:16-alpine` | **RDS PostgreSQL 16** (Multi-AZ, r6g.xlarge) | Managed backups, failover, Performance Insights, encryption at rest |
| `redis:7-alpine` | **ElastiCache Redis 7.1** (3-node replication group) | Automatic failover, TLS in-transit, snapshots |
| `qdrant/qdrant:latest` | **Qdrant StatefulSet** on EKS with gp3 EBS PVCs | No managed Qdrant on AWS; StatefulSet with persistent storage |
| API container | **EKS Deployment** (3-30 pods, HPA, PDB) | Auto-scaling, rolling updates, pod disruption budgets |
| Celery worker | **EKS Deployment** (3-15 pods, HPA) | Independent scaling from API, zone-spread |
| Celery beat | **EKS Deployment** (1 replica, singleton) | Exactly-once scheduling guarantee |
| Flower | **Optional** — replaced by Prometheus + Grafana | Enterprise monitoring stack |
| Prometheus | **kube-prometheus-stack** (Helm) | ServiceMonitor auto-discovery, AlertManager |
| Grafana | **kube-prometheus-stack** (Helm) | Pre-provisioned dashboards, RBAC |
| Docker build | **ECR** + GitHub Actions | Immutable tags, vulnerability scanning, lifecycle policies |
| `.env` file | **AWS Secrets Manager** → ExternalSecrets Operator | Zero secrets in code/config, automatic rotation |
| `docker-compose up` | **Terraform + Helm + kubectl** | Infrastructure as Code, GitOps-ready |

## Network Architecture (3-Tier VPC)

```
VPC: 10.0.0.0/16
├── Public Subnets (10.0.0.0/20, 10.0.16.0/20, 10.0.32.0/20)
│   ├── Application Load Balancer
│   ├── NAT Gateways (1 per AZ for HA)
│   └── Tagged: kubernetes.io/role/elb = 1
├── Private Subnets (10.0.64.0/20, 10.0.80.0/20, 10.0.96.0/20)
│   ├── EKS Node Group (m6i.xlarge/2xlarge)
│   ├── All application pods
│   └── Tagged: kubernetes.io/role/internal-elb = 1
└── Data Subnets (10.0.128.0/20, 10.0.144.0/20, 10.0.160.0/20)
    ├── RDS PostgreSQL (Multi-AZ)
    ├── ElastiCache Redis (replication group)
    └── No internet route (isolated)
```

## Security Architecture

### Defense in Depth

1. **Network Layer**: VPC with 3-tier subnet isolation, NACLs, Security Groups
2. **Edge Protection**: AWS WAF with rate limiting, SQL injection, XSS, geo-blocking
3. **Transport**: TLS 1.3 enforced at ALB, Redis TLS in-transit, RDS SSL
4. **Identity**: IRSA (IAM Roles for Service Accounts) — pods only get minimum AWS permissions
5. **Secrets**: AWS Secrets Manager → ExternalSecrets Operator → K8s Secrets (never in git)
6. **Container**: Non-root user, read-only filesystem, dropped capabilities, Trivy scanning
7. **Network Policies**: Default-deny with explicit allow rules per pod
8. **Encryption**: KMS encryption for RDS, EBS, S3, EKS secrets
9. **Audit**: VPC Flow Logs, EKS audit logs, CloudTrail, RDS query logging

### IAM Roles (IRSA)

| Service Account | IAM Role | Permissions |
|---|---|---|
| `fraud-api-sa` | `fraud-detection-api-pod-role` | Secrets Manager read, S3 read/write, KMS decrypt |
| `fraud-worker-sa` | `fraud-detection-worker-pod-role` | Secrets Manager read, S3 read/write |
| `external-secrets-sa` | `fraud-detection-external-secrets-role` | Secrets Manager read |
| `aws-load-balancer-controller` | `fraud-detection-alb-controller-role` | ELB, EC2, WAF, ACM |

## Scaling Strategy

### API Tier
- **HPA**: 3 → 30 pods based on CPU (70%) and memory (80%)
- **Scale-up**: Aggressive — 100% increase every 30s
- **Scale-down**: Conservative — 10% decrease every 60s, 5-min stabilization
- **PDB**: Minimum 2 pods available during disruptions
- **Topology**: Spread across 3 AZs (hard constraint)

### Worker Tier
- **HPA**: 3 → 15 pods based on CPU (75%)
- **PDB**: Minimum 2 pods
- **Grace period**: 120s for task completion on shutdown

### Database Tier
- **RDS**: Vertical scaling (instance class change), read replicas for reporting
- **Redis**: 3-node replication, automatic failover
- **Qdrant**: Single-node StatefulSet with gp3 EBS (expandable)

## Observability

### Metrics Pipeline
```
App (OTEL SDK) → Prometheus Exporter (:9464)
    → Prometheus (ServiceMonitor auto-discovery)
    → Grafana Dashboards
    → AlertManager → Slack/PagerDuty
```

### Alert Rules
| Alert | Condition | Severity |
|---|---|---|
| FraudAPIHighLatency | P99 > 500ms for 5min | warning |
| FraudAPIErrorRate | 5xx rate > 1% for 5min | critical |
| FraudAPIPodCrashLooping | Restarts in 15min | critical |
| FraudModelFallbackHigh | Fallback rate > 10% for 10min | warning |
| FraudOpenCasesHigh | Open cases > 500 for 30min | warning |

### Logs
- **EKS Control Plane**: API, audit, authenticator, controller, scheduler → CloudWatch
- **Application**: Structured JSON → stdout → CloudWatch Container Insights
- **RDS**: PostgreSQL logs + upgrade logs → CloudWatch
- **VPC**: Flow logs → CloudWatch (90-day retention)

## CI/CD Pipeline

```
Developer Push → GitHub Actions
    ├── 1. Lint (Ruff)
    ├── 2. Test (pytest + Postgres + Redis services)
    ├── 3. Security Scan (Trivy)
    └── 4. Build & Push to ECR (multi-stage, immutable tags)
         └── 5. Deploy to EKS
              ├── Run Alembic migrations (one-shot pod)
              ├── Rolling update (maxSurge=1, maxUnavailable=0)
              ├── Verify rollout (300s timeout)
              └── Smoke test (/health) — auto-rollback on failure
```

## Cost Estimate (Production)

| Resource | Spec | Monthly Cost (est.) |
|---|---|---|
| EKS Cluster | Control plane | $73 |
| EC2 Nodes | 5x m6i.xlarge (on-demand) | $770 |
| RDS PostgreSQL | r6g.xlarge, Multi-AZ, 100GB gp3 | $520 |
| ElastiCache Redis | 3x cache.r6g.large | $440 |
| NAT Gateways | 3x (one per AZ) | $100 |
| ALB | Internet-facing | $25 + data |
| S3 | Model artifacts + logs | $5 |
| Secrets Manager | ~10 secrets | $5 |
| WAF | Web ACL + rules | $10 |
| CloudWatch | Logs + metrics | $50 |
| **Total** | | **~$2,000/mo** |

> Savings opportunity: Savings Plans or Reserved Instances for EC2/RDS can reduce by 30-40%.

## Deployment Commands

```bash
# 1. Plan infrastructure
./scripts/deploy-aws.sh plan production

# 2. Apply infrastructure (VPC, EKS, RDS, Redis, S3, WAF, etc.)
./scripts/deploy-aws.sh apply production

# 3. Build and push Docker image
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
docker build -f docker/Dockerfile.production -t fraud-detection-platform:latest .
docker tag fraud-detection-platform:latest <ECR_URL>:latest
docker push <ECR_URL>:latest

# 4. Run database migrations
kubectl exec -it deploy/fraud-api -n fraud-detection -- alembic upgrade head

# 5. Seed data
kubectl exec -it deploy/fraud-api -n fraud-detection -- python -m scripts.seed_data

# 6. Monitor
kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80
# Open http://localhost:3000 (admin / fraud-ops-admin)
```

## Disaster Recovery

| Scenario | RTO | RPO | Mechanism |
|---|---|---|---|
| Pod failure | < 30s | 0 | K8s self-healing + HPA |
| AZ failure | < 2min | 0 | Multi-AZ RDS failover + pod rescheduling |
| Database corruption | < 1hr | < 5min | RDS automated backups (35-day retention) + PITR |
| Region failure | < 4hr | < 1hr | Cross-region RDS replica + S3 cross-region replication |
| Secret compromise | < 5min | 0 | Secrets Manager rotation + ExternalSecrets refresh |

## File Structure

```
terraform/
├── main.tf                          # Root: wires all modules together
├── variables.tf                     # All input variables
├── outputs.tf                       # Exported values for K8s/CI
├── production.tfvars                # Production variable values
└── modules/
    ├── vpc/main.tf                  # 3-tier VPC, NAT, flow logs
    ├── eks/main.tf                  # EKS cluster, node group, OIDC, add-ons
    ├── rds/main.tf                  # PostgreSQL 16, Multi-AZ, encrypted
    ├── elasticache/main.tf          # Redis 7.1 replication group
    ├── ecr/main.tf                  # Container registry + lifecycle
    ├── s3/main.tf                   # Model artifacts bucket
    ├── secrets/main.tf              # Secrets Manager
    ├── iam/main.tf                  # IRSA roles (API, worker, ALB, ESO)
    └── waf/main.tf                  # WAF rules (rate limit, SQLi, XSS)

k8s/base/
├── namespace.yml                    # Namespace + ResourceQuota + LimitRange
├── service-accounts.yml             # IRSA-annotated service accounts
├── external-secrets.yml             # AWS Secrets Manager → K8s Secrets
├── configmap.yml                    # Non-sensitive configuration
├── api-deployment.yml               # API Deployment + Service + HPA + PDB
├── celery-deployment.yml            # Worker + Beat deployments + HPA + PDB
├── qdrant.yml                       # StatefulSet + PVC + StorageClass
├── ingress-alb.yml                  # ALB Ingress with WAF + TLS
├── network-policies.yml             # Zero-trust network policies
└── monitoring.yml                   # ServiceMonitor + PrometheusRules

docker/
├── Dockerfile                       # Development (current)
└── Dockerfile.production            # Multi-stage, hardened, non-root

.github/workflows/
├── ci.yml                           # Lint + test (existing)
└── deploy.yml                       # Build → ECR → EKS (new)
```
