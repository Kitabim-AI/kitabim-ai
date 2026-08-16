---
name: infra-developer
description: "Use when implementing kitabim-ai shell scripts, Docker configuration, Nginx config, or GitHub Actions workflows."
---

# Infrastructure Developer Skill — Kitabim AI

You are implementing infrastructure changes: shell scripts, Docker configurations, Nginx config, CI/CD pipelines, GCP resource setup, and deployment automation for kitabim-ai. Every change must be production-safe, idempotent where possible, and follow the existing conventions.

---

## File Placement Rules

| What you're building | Where it goes |
|---------------------|---------------|
| One-time VM provisioning | `deploy/gcp/scripts/setup-vm.sh` (extend) |
| Automated deploy pipeline | `deploy/gcp/scripts/deploy.sh` (extend or alongside) |
| Env validation / safe deploy | `deploy/gcp/scripts/deploy.sh` (no separate validation script exists — `FILL_IN` values are checked manually per `deploy/gcp/PRODUCTION_DEPLOYMENT.md`) |
| Production Docker services | `deploy/gcp/docker-compose.yml` |
| Local dev Docker services | `docker-compose.yml` (root) |
| Nginx config | `deploy/gcp/nginx/conf.d/kitabim.conf` |
| Operational scripts (monitoring, DB ops, data resets) | `scripts/` (project root) |
| Local dev rebuild | `deploy/local/rebuild-and-restart.sh` |
| CI/CD pipelines | `.github/workflows/` |
| Documentation | `docs/<branch-name>/` (e.g. `docs/main/`) |

**Never** create scripts in service folders (`services/worker/`, `services/backend/`) or at the repo root.

---

## Shell Script Conventions

Every script in `scripts/` and `deploy/` must follow these rules:

### Header and safety flags
```bash
#!/bin/bash
set -euo pipefail   # exit on error, unset vars, pipe failures
```

### Colour output (use consistently)
```bash
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'  # no colour

echo -e "${GREEN}✓ Done${NC}"
echo -e "${RED}✗ Failed${NC}"
echo -e "${YELLOW}⚠ Warning${NC}"
echo -e "${BLUE}→ Step${NC}"
```

### Mandatory confirmation for destructive production operations
```bash
echo -e "${RED}WARNING: This will reset production data.${NC}"
read -p "Type 'yes' to continue: " confirm
if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 0
fi
```

### Load secrets from .env — never hardcode
```bash
ENV_FILE="deploy/gcp/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Error: $ENV_FILE not found${NC}"
    exit 1
fi
source "$ENV_FILE"
```

### Validate required variables
```bash
REQUIRED_VARS=("DATABASE_URL" "JWT_SECRET_KEY" "GEMINI_API_KEY")
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var:-}" ]; then
        echo -e "${RED}Error: $var is not set${NC}"
        exit 1
    fi
done
```

### Health check pattern (used in deploy.sh)
```bash
MAX_ATTEMPTS=30
ATTEMPT=0
until curl -sf "https://kitabim.ai/health" > /dev/null 2>&1; do
    ATTEMPT=$((ATTEMPT + 1))
    if [ $ATTEMPT -ge $MAX_ATTEMPTS ]; then
        echo -e "${RED}Health check failed after ${MAX_ATTEMPTS}s${NC}"
        exit 1
    fi
    sleep 1
done
echo -e "${GREEN}✓ Backend healthy${NC}"
```

---

## deploy.sh — Extension Pattern

When adding a new build step or deployment action to `deploy/gcp/scripts/deploy.sh`:

1. **New service to build** — add after the existing build block (actual `deploy.sh` uses plain `docker build` + a separate `docker push`, not `buildx --push`):
```bash
docker build -f Dockerfile.my-service \
    --platform linux/amd64 \
    -t "${REGISTRY}/kitabim-my-service:${IMAGE_TAG}" \
    -t "${REGISTRY}/kitabim-my-service:latest" \
    --progress=plain .

# ...later, alongside the other pushes:
docker push "${REGISTRY}/kitabim-my-service:${IMAGE_TAG}"
docker push "${REGISTRY}/kitabim-my-service:latest"
```

2. **New SSH deploy step** — add inside the `gcloud compute ssh` heredoc:
```bash
gcloud compute ssh kitabim-prod --zone=us-south1-c --command="
    cd /opt/kitabim
    docker pull ${REGISTRY}/kitabim-my-service:${IMAGE_TAG}
    docker compose up -d --no-deps my-service
"
```

3. **New secret rotation** — follow the `SECURITY_APP_ID` pattern:
```bash
NEW_VALUE=$(openssl rand -hex 16)
# Update frontend config if client-visible
sed -i "s/APP_CLIENT_ID = \".*\"/APP_CLIENT_ID = \"${NEW_VALUE}\"/" apps/frontend/src/config.ts
# Update .env
sed -i "s/MY_SECRET=.*/MY_SECRET=${NEW_VALUE}/" deploy/gcp/.env
```

---

## Docker Compose Conventions

### Adding a new service (both files must be updated)

**`docker-compose.yml`** (local dev):
```yaml
my-service:
  build:
    context: .
    dockerfile: Dockerfile.my-service
  environment:
    - DATABASE_URL=${DATABASE_URL}
    - REDIS_URL=redis://redis:6379/0
  volumes:
    - ./data:/app/data
    - ./gcs-key.json:/etc/gcs/key.json:ro
  depends_on:
    redis:
      condition: service_healthy
  deploy:
    resources:
      limits:
        memory: 512M
  restart: unless-stopped
```

**`deploy/gcp/docker-compose.yml`** (production):
```yaml
my-service:
  image: ${REGISTRY}/kitabim-my-service:${IMAGE_TAG}
  env_file: .env
  volumes:
    - app_data:/app/data
    - /etc/gcs/key.json:/etc/gcs/key.json:ro
  networks:
    - internal
  depends_on:
    - redis
  restart: always
  deploy:
    replicas: 1
    resources:
      limits:
        memory: 512M
```

**Rules:**
- Always set a memory limit via `deploy.resources.limits.memory` — never leave it unbounded (the codebase does not use the top-level `mem_limit:` shorthand)
- Always use `restart: always` in production, `restart: unless-stopped` in local
- Never bind ports in production except Nginx — use `networks: internal`
- Use `env_file: .env` in production for secrets; per-service `environment:` overrides (e.g. `REDIS_URL`, `NEO4J_URL`) are still layered on top where a container needs a different value than what's in `.env`

---

## Nginx Configuration Conventions

Config lives at `deploy/gcp/nginx/conf.d/kitabim.conf`. Unlike the per-endpoint examples below might suggest, the actual config has **one blanket `location ^~ /api/` block** that proxies everything under `/api/` to the backend, with buffering already disabled (SSE-friendly) and 300s timeouts. A new backend endpoint under `/api/` needs **no nginx change at all** — it's already covered. Only add a new `location` block for something that needs genuinely different behavior (a different upstream, different timeouts, etc.):

### New API proxy route (only if it needs different behavior than the existing blanket `/api/` block)
```nginx
location /api/my-endpoint/ {
    proxy_pass         http://backend:8000;
    proxy_set_header   Host $host;
    proxy_set_header   X-Real-IP $remote_addr;
    proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto $scheme;
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
}
```

### SSE / streaming (already handled)
The existing `/api/` block already sets `proxy_buffering off`, `proxy_cache off`, `chunked_transfer_encoding on`, and `proxy_set_header Connection ''` for the whole API surface (this is what makes RAG chat SSE streaming work), so a dedicated streaming location is only needed if a route requires a longer timeout than the default 300s:
```nginx
location /api/my-stream/ {
    proxy_pass             http://backend:8000;
    proxy_set_header       Connection '';
    proxy_http_version     1.1;
    chunked_transfer_encoding on;
    proxy_buffering        off;
    proxy_cache            off;
    proxy_read_timeout     600s;
}
```

### Static asset cache (versioned, immutable)
```nginx
location ~* ^/(?!api/).*\.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
    proxy_pass http://frontend:80;
    add_header Cache-Control "public, max-age=31536000, immutable";
}
```

**After editing Nginx config:**
```bash
# Validate syntax (on VM)
docker compose exec nginx nginx -t
# Reload without downtime (used by the certbot renewal cron in setup-vm.sh)
docker compose exec nginx nginx -s reload
# deploy.sh instead force-recreates nginx on every deploy (re-resolves upstream
# IPs and applies port-mapping changes) rather than restarting/reloading:
docker compose -f deploy/gcp/docker-compose.yml up -d --force-recreate nginx
```

---

## VM Setup — setup-vm.sh Extension Pattern

When adding new VM provisioning steps to `deploy/gcp/scripts/setup-vm.sh`:

```bash
# Always guard installs to be idempotent
if ! command -v my-tool &> /dev/null; then
    echo -e "${BLUE}→ Installing my-tool${NC}"
    apt-get install -y my-tool
    echo -e "${GREEN}✓ my-tool installed${NC}"
fi

# Directory creation with permissions
mkdir -p /opt/kitabim/my-new-dir
chown -R $USER:$USER /opt/kitabim/my-new-dir

# Cron job (avoid duplicates)
CRON_CMD="0 3 * * * /usr/bin/my-task >> /var/log/my-task.log 2>&1"
(crontab -l 2>/dev/null | grep -qF "$CRON_CMD") || \
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
```

---

## SQL Migration Scripts

All production migrations live in `packages/backend-core/migrations/NNN_description.sql` and are run with `scripts/run_migration_prod.sh`.

When writing a new migration:
```sql
-- Migration: 090_my_change.sql
-- Description: Short description of what this changes
-- Author: <name>
-- Date: YYYY-MM-DD

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'my_table' AND column_name = 'my_column'
    ) THEN
        ALTER TABLE my_table ADD COLUMN my_column TEXT;
    END IF;
END $$;

COMMIT;
```

**Rules:**
- Always `IF NOT EXISTS` — idempotent migrations are safe to re-run
- Wrap in `BEGIN; ... COMMIT;` for atomicity
- `CREATE INDEX CONCURRENTLY` must be outside a transaction — omit `BEGIN/COMMIT` for those
- Number sequentially — check the highest existing number first (89 as of this writing; each migration ships alongside a paired `NNN_rollback_description.sql`)

**Run on production:**
```bash
./scripts/run_migration_prod.sh 090
```

---

## Environment Variable Management

### .env.template pattern
Add new variables to `deploy/gcp/.env.template` with:
- `FILL_IN` as the placeholder value if required
- Actual default if safe to hardcode (e.g. `LOG_LEVEL=INFO`)
- A comment explaining what it controls

```bash
# My new feature
MY_FEATURE_ENABLED=true           # safe default
MY_API_KEY=FILL_IN                # required secret
MY_TIMEOUT_SECONDS=30             # tunable with a safe default
```

There is no automated script that greps for leftover `FILL_IN` values before a production deploy — `deploy/gcp/PRODUCTION_DEPLOYMENT.md` documents it as a manual checklist item instead. So always add new vars to the template, and always manually verify no `FILL_IN` remains in `deploy/gcp/.env` before running `deploy.sh`.

### Reading secrets in scripts (never hardcode)
```bash
# Parse DATABASE_URL into components for psql
DB_HOST=$(echo "$DATABASE_URL" | sed 's/.*@\(.*\):.*/\1/')
DB_PORT=$(echo "$DATABASE_URL" | sed 's/.*:\([0-9]*\)\/.*/\1/')
DB_NAME=$(echo "$DATABASE_URL" | sed 's/.*\/\(.*\)/\1/')
DB_USER=$(echo "$DATABASE_URL" | sed 's/.*\/\/\(.*\):.*/\1/')
DB_PASS=$(echo "$DATABASE_URL" | sed 's/.*:\/\/[^:]*:\(.*\)@.*/\1/')
PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$DB_NAME"
```

---

## GitHub Actions CI/CD — Implementation

**Note: this does not exist yet.** There is currently no `.github/workflows/` directory in this repo — all testing and deployment is manual (`deploy/gcp/scripts/deploy.sh`, run by hand from a developer machine, per `deploy/gcp/PRODUCTION_DEPLOYMENT.md`). The pattern below is a reference for *if/when* CI/CD is introduced — it is not describing an existing convention to follow, and none of the values (secrets, workflow names) are real. If asked to actually stand this up, treat it as new infrastructure (use `/infra-designer` first) rather than "extending" something that already exists.

### Workflow file structure
```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      image_tag:
        description: 'Image tag (default: git SHA)'
        required: false

env:
  REGISTRY: us-south1-docker.pkg.dev/${{ secrets.GCP_PROJECT_ID }}/kitabim
  VM_INSTANCE: kitabim-prod
  VM_ZONE: us-south1-c

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run backend tests
        run: |
          pip install -r services/backend/requirements.txt
          pytest packages/backend-core/tests/ services/backend/tests/
      - name: Run frontend tests
        run: |
          cd apps/frontend && npm ci && npm run test

  build-and-push:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - id: auth
        uses: google-github-actions/auth@v2
        with:
          credentials_json: ${{ secrets.GCP_SA_KEY }}
      - name: Configure docker auth
        run: gcloud auth configure-docker us-south1-docker.pkg.dev
      - name: Set image tag
        run: echo "IMAGE_TAG=${{ github.event.inputs.image_tag || github.sha }}" >> $GITHUB_ENV
      - name: Build and push
        run: |
          docker buildx build --platform linux/amd64 \
            -t $REGISTRY/kitabim-backend:$IMAGE_TAG \
            -t $REGISTRY/kitabim-backend:latest \
            -f Dockerfile.backend --push .
          # repeat for worker, frontend

  deploy:
    needs: build-and-push
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to VM
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.VM_HOST }}
          username: ${{ secrets.VM_USER }}
          key: ${{ secrets.VM_SSH_KEY }}
          script: |
            cd /opt/kitabim
            git pull origin main
            docker pull ${{ env.REGISTRY }}/kitabim-backend:${{ env.IMAGE_TAG }}
            docker compose up -d --no-deps backend worker frontend
            docker compose restart nginx
      - name: Health check
        run: |
          for i in $(seq 1 30); do
            curl -sf https://kitabim.ai/api/health && exit 0
            sleep 1
          done
          exit 1
```

### Required GitHub Secrets
| Secret | Value |
|--------|-------|
| `GCP_SA_KEY` | GCP service account JSON (Artifact Registry write + Compute SSH) |
| `GCP_PROJECT_ID` | GCP project ID |
| `VM_HOST` | VM external IP (`<PRODUCTION_VM_IP>`) |
| `VM_USER` | SSH username on VM |
| `VM_SSH_KEY` | Private SSH key for VM access |

### Preferred: Workload Identity Federation (no long-lived keys)
```yaml
- id: auth
  uses: google-github-actions/auth@v2
  with:
    workload_identity_provider: 'projects/PROJECT_NUM/locations/global/workloadIdentityPools/github/providers/github'
    service_account: 'github-actions@PROJECT_ID.iam.gserviceaccount.com'
```

---

## Monitoring Scripts — Extension Pattern

When adding a new metric to `scripts/monitor.sh` or `scripts/monitor-local.sh`:

```bash
# New metric block — follows existing pattern
echo ""
echo "=== My New Metric ==="
MY_VALUE=$(docker exec redis redis-cli MY_COMMAND 2>/dev/null || echo "N/A")
echo "Value: ${MY_VALUE}"

# With threshold alerting
if [ "$MY_VALUE" != "N/A" ] && [ "$MY_VALUE" -gt 100 ]; then
    echo -e "${RED}⚠ ALERT: Value exceeds threshold${NC}"
elif [ "$MY_VALUE" != "N/A" ] && [ "$MY_VALUE" -gt 50 ]; then
    echo -e "${YELLOW}⚠ WARNING: Value elevated${NC}"
else
    echo -e "${GREEN}✓ OK${NC}"
fi
```

---

## Checklist — Adding a New Infrastructure Component

1. **Design** — fill out the designer skill questions first (blast radius, rollback, cost)
2. **Docker Compose** — add to both `docker-compose.yml` (local) and `deploy/gcp/docker-compose.yml` (prod) with memory limits
3. **Nginx** — add route in `kitabim.conf` if it needs HTTP access; validate with `nginx -t`
4. **Environment** — add vars to `deploy/gcp/.env.template`; add to `packages/backend-core/app/core/config.py` `Settings`
5. **VM provisioning** — add setup steps to `setup-vm.sh` with idempotency guards
6. **deploy.sh** — add build and deploy steps for new images; add health check if applicable
7. **Monitoring** — add metric to `scripts/monitor.sh` with alert thresholds
8. **Migration** — if DB change, create `NNN_description.sql` with `IF NOT EXISTS` guards
9. **Documentation** — write a doc in `docs/<branch-name>/` covering what was added, why, and how to operate it
10. **Test** — test the full flow locally with `./deploy/local/rebuild-and-restart.sh` before touching production

---

## Common Mistakes

| Mistake | Why it's wrong | Fix |
|---------|---------------|-----|
| Hardcoding secrets in scripts | Leaks into git history | Always `source .env` or use `$SECRET` env var |
| No `set -euo pipefail` | Errors are silently swallowed | Always first line after `#!/bin/bash` |
| No `FILL_IN` check before prod deploy | Deploys with unset secrets | Manually grep `deploy/gcp/.env` for `FILL_IN` before running `deploy.sh` — no automated check exists |
| Port exposed directly on VM | Bypasses Nginx security headers and SSL | Route via Nginx proxy |
| No memory limit on Docker service | Service can OOM the VM | Always set `deploy.resources.limits.memory` matching the VM budget |
| Running migration without confirmation | Can't undo on prod | Require `yes` prompt; dry-run first |
| Building images for wrong arch on M1 Mac | Fails on VM (linux/amd64) | Always `--platform linux/amd64` |
| SSH key in CI stored as plain env var | Exposed in logs | Use GitHub Secrets; never `echo $SSH_KEY` (N/A today — no CI exists yet) |
| No health check after deploy | Silent broken deploy | Always verify `/health` post-deploy (the route is mounted at the app root, not under `/api/`) |
| Editing `.env` directly on VM without backup | One typo kills prod | `cp .env .env.backup` before editing |
