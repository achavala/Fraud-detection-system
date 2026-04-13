#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# Fraud Detection Platform — AWS Deployment Bootstrap
# Usage: ./scripts/deploy-aws.sh [plan|apply|destroy]
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
TERRAFORM_DIR="$PROJECT_ROOT/terraform"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()   { echo -e "${RED}[ERROR]${NC} $1"; }

ACTION="${1:-plan}"
ENV="${2:-production}"

# --- Pre-flight checks ---

check_prerequisites() {
    info "Checking prerequisites..."
    local missing=()

    command -v aws >/dev/null 2>&1 || missing+=("aws-cli")
    command -v terraform >/dev/null 2>&1 || missing+=("terraform")
    command -v kubectl >/dev/null 2>&1 || missing+=("kubectl")
    command -v helm >/dev/null 2>&1 || missing+=("helm")
    command -v docker >/dev/null 2>&1 || missing+=("docker")

    if [ ${#missing[@]} -gt 0 ]; then
        err "Missing required tools: ${missing[*]}"
        exit 1
    fi

    aws sts get-caller-identity >/dev/null 2>&1 || { err "AWS credentials not configured"; exit 1; }
    ok "All prerequisites satisfied"
}

# --- Terraform state backend ---

init_terraform_backend() {
    info "Ensuring Terraform state backend exists..."
    local BUCKET="fraud-detection-terraform-state"
    local TABLE="fraud-detection-terraform-locks"

    if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
        info "Creating S3 state bucket: $BUCKET"
        aws s3api create-bucket --bucket "$BUCKET" --region us-east-1
        aws s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
        aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
            '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"aws:kms"}}]}'
        aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
            BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
    fi

    if ! aws dynamodb describe-table --table-name "$TABLE" >/dev/null 2>&1; then
        info "Creating DynamoDB lock table: $TABLE"
        aws dynamodb create-table \
            --table-name "$TABLE" \
            --attribute-definitions AttributeName=LockID,AttributeType=S \
            --key-schema AttributeName=LockID,KeyType=HASH \
            --billing-mode PAY_PER_REQUEST
    fi

    ok "Terraform backend ready"
}

# --- Terraform ---

run_terraform() {
    info "Running Terraform $ACTION..."
    cd "$TERRAFORM_DIR"

    terraform init -upgrade

    case "$ACTION" in
        plan)
            terraform plan -var-file="${ENV}.tfvars" -out=tfplan
            ok "Plan saved to tfplan. Run './scripts/deploy-aws.sh apply' to apply."
            ;;
        apply)
            if [ -f tfplan ]; then
                terraform apply tfplan
            else
                terraform apply -var-file="${ENV}.tfvars" -auto-approve
            fi
            ok "Infrastructure provisioned"
            ;;
        destroy)
            warn "This will DESTROY all infrastructure!"
            terraform destroy -var-file="${ENV}.tfvars"
            ;;
        *)
            err "Unknown action: $ACTION (use plan, apply, or destroy)"
            exit 1
            ;;
    esac
}

# --- Post-provision: Install K8s components ---

install_k8s_components() {
    info "Installing Kubernetes components on EKS..."
    local CLUSTER_NAME
    CLUSTER_NAME=$(terraform -chdir="$TERRAFORM_DIR" output -raw eks_cluster_name)

    aws eks update-kubeconfig --name "$CLUSTER_NAME" --region us-east-1

    # AWS Load Balancer Controller
    info "Installing AWS Load Balancer Controller..."
    helm repo add eks https://aws.github.io/eks-charts 2>/dev/null || true
    helm repo update
    helm upgrade --install aws-load-balancer-controller eks/aws-load-balancer-controller \
        --namespace kube-system \
        --set clusterName="$CLUSTER_NAME" \
        --set serviceAccount.create=true \
        --set serviceAccount.annotations."eks\.amazonaws\.com/role-arn"="$(terraform -chdir="$TERRAFORM_DIR" output -raw alb_controller_role_arn)"

    # External Secrets Operator
    info "Installing External Secrets Operator..."
    helm repo add external-secrets https://charts.external-secrets.io 2>/dev/null || true
    helm upgrade --install external-secrets external-secrets/external-secrets \
        --namespace external-secrets --create-namespace \
        --set installCRDs=true

    # Prometheus + Grafana (kube-prometheus-stack)
    info "Installing Prometheus + Grafana..."
    helm repo add prometheus-community https://prometheus-community.github.io/helm-charts 2>/dev/null || true
    helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
        --namespace monitoring --create-namespace \
        --set grafana.adminPassword="fraud-ops-admin" \
        --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false

    # Metrics Server (for HPA)
    info "Installing Metrics Server..."
    helm upgrade --install metrics-server metrics-server/metrics-server \
        --namespace kube-system 2>/dev/null || \
    kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml 2>/dev/null || true

    ok "All Kubernetes components installed"
}

# --- Deploy application ---

deploy_application() {
    info "Deploying Fraud Detection Platform..."
    local ECR_URL SECRETS_ARN

    ECR_URL=$(terraform -chdir="$TERRAFORM_DIR" output -raw ecr_repository_url)
    SECRETS_ARN=$(terraform -chdir="$TERRAFORM_DIR" output -raw secrets_manager_arn)

    export ECR_REPOSITORY_URL="$ECR_URL"
    export IMAGE_TAG="latest"
    export SECRETS_MANAGER_ARN="$SECRETS_ARN"
    export API_POD_ROLE_ARN=$(terraform -chdir="$TERRAFORM_DIR" output -raw api_pod_role_arn)
    export WORKER_POD_ROLE_ARN=$(terraform -chdir="$TERRAFORM_DIR" output -raw worker_pod_role_arn)

    for f in "$PROJECT_ROOT"/k8s/base/*.yml; do
        info "Applying $(basename "$f")..."
        envsubst < "$f" | kubectl apply -f -
    done

    info "Waiting for API rollout..."
    kubectl rollout status deployment/fraud-api --namespace=fraud-detection --timeout=300s

    ok "Fraud Detection Platform deployed to EKS!"
    echo ""
    info "Endpoints:"
    echo "  API:       kubectl get ingress -n fraud-detection"
    echo "  Grafana:   kubectl port-forward -n monitoring svc/prometheus-grafana 3000:80"
    echo "  Qdrant:    kubectl port-forward -n fraud-detection svc/qdrant 6333:6333"
}

# --- Main ---

echo "============================================"
echo " Fraud Detection Platform — AWS Deployment"
echo " Action: $ACTION | Environment: $ENV"
echo "============================================"
echo ""

check_prerequisites

case "$ACTION" in
    plan|destroy)
        init_terraform_backend
        run_terraform
        ;;
    apply)
        init_terraform_backend
        run_terraform
        install_k8s_components
        deploy_application
        ;;
    *)
        err "Usage: $0 [plan|apply|destroy] [production|staging]"
        exit 1
        ;;
esac
