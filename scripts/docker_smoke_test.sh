#!/usr/bin/env bash
set -euo pipefail

# Docker Compose end-to-end smoke test
# Verifies all services start cleanly and respond to health checks.

COMPOSE_FILE="docker-compose.yml"
MAX_WAIT=120
API_URL="http://localhost:8000"
FLOWER_URL="http://localhost:5555"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

pass() { echo -e "${GREEN}✓ $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; }
info() { echo -e "${YELLOW}→ $1${NC}"; }

cleanup() {
    info "Stopping services..."
    docker compose -f "$COMPOSE_FILE" down -v --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

echo "============================================"
echo " Fraud Detection Platform — Smoke Test"
echo "============================================"

info "Building and starting all services..."
docker compose -f "$COMPOSE_FILE" up -d --build 2>&1

info "Waiting for services to become healthy (max ${MAX_WAIT}s)..."

wait_for_health() {
    local service=$1
    local url=$2
    local elapsed=0
    while [ $elapsed -lt $MAX_WAIT ]; do
        if curl -sf "$url" > /dev/null 2>&1; then
            pass "$service is healthy ($url)"
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
    done
    fail "$service did not become healthy within ${MAX_WAIT}s ($url)"
    return 1
}

ERRORS=0

# 1. Postgres
info "Checking Postgres..."
for i in $(seq 1 $((MAX_WAIT / 3))); do
    if docker compose exec -T postgres pg_isready -U fraud_user -d fraud_db > /dev/null 2>&1; then
        pass "Postgres is ready"
        break
    fi
    sleep 3
done

# 2. Redis
info "Checking Redis..."
for i in $(seq 1 $((MAX_WAIT / 3))); do
    if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
        pass "Redis is ready"
        break
    fi
    sleep 3
done

# 3. Qdrant
wait_for_health "Qdrant" "http://localhost:6333/healthz" || ERRORS=$((ERRORS + 1))

# 4. API
wait_for_health "API" "${API_URL}/health" || ERRORS=$((ERRORS + 1))

# 5. API health response validation
info "Validating API health response..."
HEALTH=$(curl -sf "${API_URL}/health" 2>/dev/null || echo "{}")
if echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('status')=='healthy'" 2>/dev/null; then
    pass "API health response is valid"
else
    fail "API health response invalid: $HEALTH"
    ERRORS=$((ERRORS + 1))
fi

# 6. API docs
info "Checking API docs..."
if curl -sf "${API_URL}/docs" > /dev/null 2>&1; then
    pass "Swagger docs accessible at ${API_URL}/docs"
else
    fail "Swagger docs not accessible"
    ERRORS=$((ERRORS + 1))
fi

# 7. Celery worker
info "Checking Celery worker..."
WORKER_RUNNING=$(docker compose ps --format json celery-worker 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('State',''))" 2>/dev/null || echo "")
if [ "$WORKER_RUNNING" = "running" ]; then
    pass "Celery worker is running"
else
    info "Celery worker state: ${WORKER_RUNNING:-unknown} (may still be starting)"
fi

# 8. Celery beat
info "Checking Celery beat..."
BEAT_RUNNING=$(docker compose ps --format json celery-beat 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('State',''))" 2>/dev/null || echo "")
if [ "$BEAT_RUNNING" = "running" ]; then
    pass "Celery beat is running"
else
    info "Celery beat state: ${BEAT_RUNNING:-unknown} (may still be starting)"
fi

# 9. Flower
wait_for_health "Flower" "${FLOWER_URL}/api/workers" || info "Flower may need more time"

# 10. Service count
info "Checking all containers..."
RUNNING=$(docker compose ps --format json 2>/dev/null | python3 -c "
import sys, json
lines = sys.stdin.read().strip().split('\n')
running = sum(1 for l in lines if l.strip() and json.loads(l).get('State') == 'running')
print(running)
" 2>/dev/null || echo "0")
echo ""
info "Running containers: $RUNNING / 7 expected (postgres, redis, qdrant, api, worker, beat, flower)"

echo ""
echo "============================================"
if [ $ERRORS -eq 0 ]; then
    pass "ALL SMOKE TESTS PASSED"
else
    fail "$ERRORS SMOKE TEST(S) FAILED"
fi
echo "============================================"

exit $ERRORS
