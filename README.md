# Kitabim.AI Monorepo

The intelligent Uyghur Digital Library platform for OCR, curation, and RAG-powered reading.

## Structure

- `/services/backend`: FastAPI API service (runs shared backend core).
- `/packages/backend-core`: Shared Python backend package.
- `/services/worker`: ARQ worker that processes background OCR/embedding/RAG jobs (uses backend-core).
- `/apps/frontend`: React UI (Vite).
- `/packages/shared`: Shared TS types/utilities.
- `/data`: Persistent storage created at runtime (ignored by git).
  - `uploads/`: Original PDF files.
  - `covers/`: Extracted book cover images.

- `AGENTS.md` files in the repo root and each service provide guidance for automated changes.

## Local Development (Docker Compose)

### Prerequisites

- **Docker Desktop** (or Docker Engine + Docker Compose)

### Environment Variables

All configuration is managed via the root-level `.env` file. See `.env.template` for available variables.

Notes:
- `DATABASE_URL` connects to your **host PostgreSQL** via `host.docker.internal:5432`.
- `GEMINI_API_KEY` is required for AI features.
- Local storage at `./data` is mounted to the containers for persistent uploads and covers.

### Quickstart: Start the App Locally

Follow these steps to get the environment running on your machine:

**1. Prepare Environment**
Copy the template and fill in your keys (especially `GEMINI_API_KEY`):
```bash
cp .env.template .env
```

**2. Database Prerequisites**
Ensure **PostgreSQL** is running on your host machine at port `5432`. The app connects via `host.docker.internal`.

**3. Launch Services**
Build and start all services in the background:
```bash
./deploy/local/rebuild-and-restart.sh all
```
*Tip: Use `./deploy/local/rebuild-and-restart.sh [frontend|backend|worker]` to rebuild only specific services.*

**4. Access the App**
- **Web UI**: [http://localhost:30080](http://localhost:30080)
- **API Docs**: [http://localhost:30800/docs](http://localhost:30800/docs)
- **Health Check**: [http://localhost:30800/health](http://localhost:30800/health)

---

### Start / Stop / Restart

```bash
# Start
docker compose up -d

# Stop
docker compose down

# Restart a specific service
./deploy/local/rebuild-and-restart.sh backend

# Rebuild and restart all services
./deploy/local/rebuild-and-restart.sh all
```

### Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f backend
```

### Status

```bash
docker compose ps
```

### Health Checks

```bash
curl -s http://localhost:30800/health
```

### Tests

```bash
npm test
python3.13 -m pytest services/backend/tests
```

### Troubleshooting

- **host.docker.internal not resolving**: Ensure you are using Docker Desktop or have configured the `host-gateway` in your Docker setup.
- **Backend not ready**: Check logs with `docker compose logs backend`.

# Technology Stack

- **Frontend**: React 19, Vite 6, Tailwind (CDN), Lucide, pdf.js.
- **Backend**: FastAPI, PostgreSQL (asyncpg), pgvector, PyMuPDF, LangChain, `langchain-google-genai`, `httpx`, `numpy`.
- **Queue/Worker**: Redis 7+ + ARQ.
- **Caching**: Redis (shared with queue).
- **Microservices**: Backend (FastAPI), Worker (ARQ).

- **Production**: Automated deployment using GCP Artifact Registry and Docker Compose on GCE.
  - Deployment Script: `./deploy/gcp/scripts/deploy.sh [IMAGE_TAG]`
  - See [Production Deployment Guide](docs/PRODUCTION_DEPLOYMENT.md) for details.
