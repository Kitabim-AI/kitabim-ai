# Infrastructure Designer Skill — Kitabim AI

You are designing infrastructure changes, new GCP resources, CI/CD pipelines, and deployment architecture for kitabim-ai. Before proposing changes, understand the current topology completely. Every design decision must account for cost, security, rollback safety, and the operational burden on a single-person team.

---

## Current Infrastructure Topology

```
Internet
  │
  ▼
GCP VM: kitabim-prod (e2-standard-2, us-south1-c)
  IP: 34.174.120.98
  │
  ├── Nginx (80/443) ── Let's Encrypt SSL (auto-renew via cron 3am)
  │     ├── /api/* ──────────────────────► backend:8000
  │     ├── /static/* (immutable cache) ► frontend:80
  │     └── /* (SPA fallback) ──────────► frontend:80
  │
  ├── Docker internal network (no ports exposed except Nginx 80/443)
  │     ├── backend (FastAPI :8000) — 1 GB limit
  │     ├── worker  (arq)           — 1 GB limit
  │     ├── frontend (Nginx SPA)    — 256 MB limit
  │     └── redis   (:6379)         — 512 MB limit, appendonly persistence
  │
  ├── Volume: /mnt/kitabim-data (persistent disk /dev/sdb)
  │     └── /app/data  ← shared between backend + worker
  │
  └── /etc/gcs/key.json  ← GCS service account key (on VM)

External Services (not on VM):
  ├── Cloud SQL (PostgreSQL) — private IP 10.158.0.5:5432
  ├── GCS data bucket  — ai-kitabim-prod-data-bkt  (PDFs)
  ├── GCS media bucket — ai-kitabim-prod-media-bkt (covers)
  ├── Artifact Registry — us-south1-docker.pkg.dev/{PROJECT_ID}/kitabim
  └── Gemini API (external)
```

---

## GCP Resources in Use

| Resource | Name / ID | Notes |
|----------|-----------|-------|
| Compute Engine VM | `kitabim-prod` | e2-standard-2, us-south1-c |
| Cloud SQL | private IP `10.158.0.5` | PostgreSQL, pgvector extension |
| GCS bucket (data) | `ai-kitabim-prod-data-bkt` | PDFs, private |
| GCS bucket (media) | `ai-kitabim-prod-media-bkt` | Covers, partially public |
| Artifact Registry | `us-south1-docker.pkg.dev/{PROJECT_ID}/kitabim` | Docker images |
| SSL | Let's Encrypt (certbot) | Auto-renews via cron |
| DNS | External (points to VM IP) | Not managed in GCP |

---

## Current Deployment Flow

```
Developer machine
  1. ./deploy/gcp/scripts/deploy.sh [IMAGE_TAG]
       ├── Rotate SECURITY_APP_ID (openssl rand -hex 16)
       ├── Build linux/amd64 images (DOCKER_BUILDKIT=1)
       │     ├── kitabim-backend:TAG + :latest
       │     ├── kitabim-worker:TAG + :latest
       │     └── kitabim-frontend:TAG + :latest
       ├── Push to Artifact Registry
       └── SSH to kitabim-prod
             ├── Sync deploy/gcp/.env
             ├── git pull origin/main
             ├── docker pull (all 3 images)
             ├── docker compose up -d (backend, worker, frontend)
             ├── docker compose restart nginx
             └── Health check: curl /api/health (30s timeout)
```

**IMAGE_TAG default**: `git rev-parse --short HEAD` (7-char git SHA)

---

## Secret & Config Management

| Secret | Storage | Rotation |
|--------|---------|----------|
| `deploy/gcp/.env` | VM only, never committed | Manual, on security events |
| `SECURITY_APP_ID` | `.env` + `apps/frontend/src/config.ts` | Auto-rotated every deploy |
| `JWT_SECRET_KEY` | `.env` | Manual, every 90 days |
| `IP_SALT` | `.env` | Manual, every 90 days |
| GCS service account key | `/etc/gcs/key.json` on VM | Manual |
| Gemini API key | `.env` | Manual |
| OAuth secrets | `.env` | Manual |

Template for new secrets: `.env.template` with `FILL_IN` placeholders. The `deploy_security_fixes.sh` script validates no `FILL_IN` remains before deploying.

---

## Designing a New Infrastructure Change

Work through these questions before writing any scripts or config:

### 1. Does it need a new GCP resource?
- New GCP service (Cloud Run, Pub/Sub, etc.) → justify cost vs. running on the VM
- New bucket → decide public vs. private access; add bucket name to `Settings` in `config.py`
- New service account → minimum-privilege IAM; key mounted to `/etc/gcs/` on VM
- New VM → consider whether horizontal scaling is actually needed or if vertical is cheaper

### 2. Does it need a new Docker service?
- Add to both `docker-compose.yml` (local) and `deploy/gcp/docker-compose.yml` (prod)
- Assign memory limits — VM has ~8 GB total; stay within budget
- Put it on the internal Docker network — never expose ports directly
- If it needs shared data, mount the same `app_data` volume

### 3. Is it a new script or a CI/CD step?
- **One-time setup** → `deploy/gcp/scripts/setup-vm.sh` (VM provisioning) or new `scripts/setup-*.sh`
- **Deployment automation** → `deploy/gcp/scripts/deploy.sh` (extend, or add alongside)
- **Operational/maintenance** → `scripts/` root; never in `deploy/` or service folders
- **CI/CD pipeline** → `.github/workflows/` (GitHub Actions); build/test/push/deploy stages

### 4. CI/CD design principles for this project
- **Build once, deploy everywhere**: build `linux/amd64` images locally or in CI, push to Artifact Registry, pull on VM
- **No secrets in CI**: use GitHub Actions secrets or Workload Identity Federation — never commit `.env`
- **Health-gated deployment**: deploy only if `/api/health` passes post-deploy
- **Rollback by tag**: every image is tagged with git SHA; rollback = `docker pull :previous-sha`
- **Single deployment unit**: all 3 services (backend, worker, frontend) deploy together unless explicitly decoupled
- **Idempotent deploys**: running `deploy.sh` twice with the same tag should be safe

### 5. What is the blast radius of a failure?
- VM goes down → all services go down (no redundancy currently — acceptable for this scale)
- Cloud SQL goes down → backend + worker fail; Redis and frontend still up
- Redis goes down → job queue lost; backend cache lost; auth cache lost (sessions re-validate from DB)
- GCS goes down → file uploads fail; PDF processing fails; covers unavailable
- Gemini API goes down → circuit breaker opens; RAG chat disabled; OCR pipeline stalls

### 6. Does it affect the persistent data disk?
- `/mnt/kitabim-data` is a separate attached disk — not the VM boot disk
- New directories under it must be created in `setup-vm.sh` and have correct permissions
- Never write large files to the VM boot disk — always use the data mount

### 7. What is the rollback plan?
- Docker services → `docker compose up -d --no-deps service:previous-tag`
- Nginx config → git revert + `docker compose restart nginx`
- Database migration → migration must be reversible; write a down-migration if needed
- VM config changes → document manual reversal steps before applying

---

## Adding a New CI/CD Pipeline (GitHub Actions)

When designing a CI/CD workflow, follow this structure:

```
.github/workflows/
  deploy.yml        ← triggered on push to main or manual dispatch
  test.yml          ← triggered on PR (unit + integration tests)
  security.yml      ← scheduled (weekly secret scanning, dependency audit)
```

### Recommended deploy.yml stages
```
1. test          — run backend pytest + frontend vitest (fast gate)
2. build         — docker buildx linux/amd64, push to Artifact Registry
3. migrate       — run pending SQL migrations via scripts/run_migration_prod.sh
4. deploy        — SSH to VM, pull images, restart services
5. verify        — health check /api/health with retry
6. notify        — Slack/email on failure (optional)
```

### Authentication to GCP from GitHub Actions
- Use **Workload Identity Federation** (preferred) — no long-lived keys
- Or: store GCP service account JSON as a GitHub Secret — simpler but less secure
- Artifact Registry access: `google-github-actions/auth` + `google-github-actions/setup-gcloud`

### VM SSH from GitHub Actions
- Store the VM SSH private key as a GitHub Secret (`GCP_SSH_PRIVATE_KEY`)
- Use `appleboy/ssh-action` or `gcloud compute ssh` with `--tunnel-through-iap` for IAP access (no public SSH port needed)

---

## Scaling Considerations

| Bottleneck | Current state | Design option |
|------------|--------------|---------------|
| Single VM | All services on one host | Add VM replica + load balancer (GCP HTTPS LB) |
| Worker throughput | 1 replica, QUEUE_MAX_JOBS=2 | Add worker VM replicas (safe — `FOR UPDATE SKIP LOCKED`) |
| PostgreSQL connections | Pool 5/5 (prod) | PgBouncer sidecar or increase Cloud SQL tier |
| Redis memory | 512 MB | Increase maxmemory; or separate cache vs queue Redis |
| Image build time | Local build on dev machine | Move to GitHub Actions with layer caching |
| Nginx static assets | VM serves compiled Vite output | Add Cloud CDN in front of Nginx |

**Do not over-engineer**: the current e2-standard-2 + single Redis + Cloud SQL setup handles the current load. Add complexity only when a specific bottleneck is measured.

---

## Security Boundaries

| Boundary | Enforcement | Design rule |
|----------|-------------|-------------|
| Internet → VM | Nginx (80/443 only) | Never add new open ports; use IAP for SSH |
| VM → Cloud SQL | Private IP (VPC) | Connection string in `.env` only; never hardcode |
| VM → GCS | Service account key | Minimum IAM: `storage.objectAdmin` on specific buckets |
| VM → Gemini | API key in `.env` | Never log; circuit breaker prevents runaway spend |
| Between containers | Internal Docker network | No service binds to `0.0.0.0` except Nginx |
| Frontend → backend | `/api/*` proxy via Nginx | No CORS bypass; `enforce_app_id` header required |

---

## Local vs Production Differences

| Aspect | Local dev | Production (GCP) |
|--------|-----------|-----------------|
| Postgres | `host.docker.internal:5532` | Cloud SQL `10.158.0.5:5432` |
| Redis persistence | None (ephemeral) | `appendonly yes`, `appendfsync everysec` |
| Redis memory | 256 MB | 512 MB |
| File storage | `./data` bind mount | `/mnt/kitabim-data` named volume |
| Images | Built locally (`docker compose build`) | Pulled from Artifact Registry |
| Nginx | Not present (ports exposed directly) | Present (SSL, proxy, security headers) |
| Secrets | `.env` at repo root | `deploy/gcp/.env` on VM |
| Deploy | `./deploy/local/rebuild-and-restart.sh` | `./deploy/gcp/scripts/deploy.sh` |

---

## File Layout Reference

```
deploy/
  gcp/
    docker-compose.yml          ← production service definitions
    .env.template               ← template; fill to create .env
    nginx/conf.d/kitabim.conf   ← Nginx SSL + proxy config
    scripts/
      setup-vm.sh               ← one-time VM provisioning
      deploy.sh                 ← automated build + push + deploy
      deploy_security_fixes.sh  ← manual deploy with env validation
  local/
    rebuild-and-restart.sh      ← local dev rebuild (single or all services)

scripts/                        ← operational / maintenance scripts
  monitor.sh                    ← production health monitoring
  monitor-local.sh              ← local dev monitoring
  run_migration_prod.sh         ← run a specific SQL migration on prod
  reset_spell_check_prod.sh     ← production data reset (with confirmation)
  setup-gcp-vm.sh               ← alternative minimal VM setup

docker-compose.yml              ← local dev (all services)
Dockerfile.backend              ← backend image
Dockerfile.worker               ← worker image
apps/frontend/Dockerfile        ← frontend image
```
