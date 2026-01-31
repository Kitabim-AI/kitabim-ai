# Kitabim.AI Monorepo

The intelligent Uyghur Digital Library platform for OCR, curation, and RAG-powered reading.

## Structure

- `/services/backend`: FastAPI API service (runs shared backend core).
- `/packages/backend-core`: Shared Python backend package.
  - `app/api`: Book and chat endpoints.
  - `app/services`: PDF OCR, embeddings, spell check, and AI helpers.
  - `app/langchain`: LangChain-native chains and model/embedding adapters.
  - `app/core`: Settings and prompts.
  - `app/db`: MongoDB connection and repositories.
  - `app/models`: Pydantic schemas.
  - `app/utils`: Text cleaning helpers.
- `/services/uyghurocr`: Local OCR service (FastAPI) using Tesseract + ONNX.
  - `logic`: OCR and PDF processing logic.
  - `tessdata`: Tesseract language data.
- `/services/worker`: ARQ worker that processes background OCR/embedding/RAG jobs (uses backend-core).
- `/apps/frontend`: React UI (Vite).
  - `src/components`: Library, Reader, Admin, Chat, Spell Check, layout/common UI.
  - `src/hooks`: Global state and data fetching.
  - `src/services`: API clients and Gemini helpers.
- `/packages/shared`: Shared TS types/utilities.
- `/data`: Persistent storage created at runtime (ignored by git).
  - `uploads/`: Original PDF files.
  - `covers/`: Extracted book cover images.
- `/infra/k8s/docker-desktop`: Docker Desktop Kubernetes manifests.
- `AGENTS.md` files in the repo root and each service provide guidance for automated changes.

### Backend Core Layout
```
/packages/backend-core
  /app
    /api
    /services
    /langchain
    /core
    /db
    /models
    /utils
```

### Architecture Diagram
```mermaid
flowchart LR
  FE[Frontend<br/>React/Vite] -->|/api| BE[Backend API<br/>FastAPI]
  BE -->|jobs| RQ[(Redis/ARQ)]
  RQ --> WK[Worker<br/>ARQ]
  BE --> DB[(MongoDB)]
  WK --> DB
  BE -.->|OCR (optional)| OCR[UyghurOCR]
  WK -.->|OCR (optional)| OCR
  BE <-->|files| DATA[(data/ volume)]
  WK <-->|files| DATA
```

## Core Features

- **SHA-256 deduplication** to avoid re-processing identical PDFs.
- **Parallel OCR pipeline** with resumable tasks, cover extraction, and batch embeddings.
- **Gemini or local OCR** (switchable via `OCR_PROVIDER`).
- **RAG chat** per book or global, with work-aware context and citations by page.
- **Spell check & correction workflow** for OCR cleanup and embedding regeneration.
- **Admin tools** for reprocessing, deletion, author/volume/category edits, and cover uploads.
- **RTL reader** with inline page editing and page-level reprocess.

## Local Development (Docker Desktop Kubernetes)

### Prerequisites

- **Docker Desktop** with Kubernetes enabled + **kubectl**
- **Note**: Docker Compose is not supported for local development; use Docker Desktop Kubernetes.

### Environment Variables

Create a `.env` file in the repo root:

```env
GEMINI_API_KEY=your_google_gemini_api_key
GEMINI_MODEL_NAME=gemini-3-flash-preview
GEMINI_CATEGORIZATION_MODEL=gemini-3-flash-preview
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001
MONGODB_URL=mongodb://localhost:27017
MONGODB_DATABASE=kitabim_ai_db
MAX_PARALLEL_PAGES=5
OCR_PROVIDER=gemini
LOCAL_OCR_URL=http://localhost:8001
OCR_MAX_RETRIES=4
RAG_SCORE_THRESHOLD=0.35
RAG_TOP_K=12
RAG_FALLBACK_K=8
RAG_MAX_CHARS_PER_BOOK=4000
DATA_DIR=./data
LANGCHAIN_CACHE=false
LANGCHAIN_TRACING=false
LANGCHAIN_PROJECT=kitabim-local
RAG_EVAL_ENABLED=false
LLM_CB_FAILURE_THRESHOLD=5
LLM_CB_RECOVERY_SECONDS=30
LLM_CB_HALF_OPEN_MAX_CALLS=1
REDIS_URL=redis://localhost:6379/0
QUEUE_MAX_JOBS=2
QUEUE_JOB_TIMEOUT=1800
QUEUE_MAX_RETRIES=3
JOB_LOCK_TTL_SECONDS=1800
```

Notes:
- `GEMINI_API_KEY` is used by the backend only. The frontend proxies AI calls to the backend.
- Set `OCR_PROVIDER=local` to route OCR to the local OCR service.
- For Docker Desktop Kubernetes, copy required values into `infra/k8s/docker-desktop/secret.yaml` (secrets) and `infra/k8s/docker-desktop/configmap.yaml` (non-secrets).

### Docker Desktop Kubernetes Quickstart

1. Enable Kubernetes in Docker Desktop (Settings → Kubernetes) and set your context:

```bash
kubectl config use-context docker-desktop
```

2. Update `infra/k8s/docker-desktop/pv.yaml` if your repo path differs (for the shared `/data` mount).
3. Build images:

```bash
docker build -t kitabim-backend:local -f services/backend/Dockerfile .
docker build -t kitabim-worker:local -f services/worker/Dockerfile .
docker build -t kitabim-uyghurocr:local services/uyghurocr
docker build -t kitabim-frontend:local -f apps/frontend/Dockerfile .
```

4. Apply manifests:

```bash
kubectl apply -k infra/k8s/docker-desktop
```

5. Update `infra/k8s/docker-desktop/secret.yaml` with your `GEMINI_API_KEY` and re-apply if needed.
6. Access services:
   - Frontend: `http://localhost:30080`
   - Backend: `kubectl -n kitabim port-forward svc/backend 8000:8000`

### Start / Stop / Restart

```bash
# Start (apply manifests)
kubectl apply -k infra/k8s/docker-desktop

# Stop (delete namespace)
kubectl delete namespace kitabim

# Restart (rolling restart all deployments)
kubectl -n kitabim rollout restart deployment/backend deployment/worker deployment/frontend deployment/uyghurocr deployment/mongo deployment/redis
```

### Logs

```bash
# Backend
kubectl -n kitabim logs deployment/backend --tail=200 -f

# Worker
kubectl -n kitabim logs deployment/worker --tail=200 -f

# Frontend (nginx)
kubectl -n kitabim logs deployment/frontend --tail=200 -f

# UyghurOCR
kubectl -n kitabim logs deployment/uyghurocr --tail=200 -f

# MongoDB
kubectl -n kitabim logs deployment/mongo --tail=200 -f

# Redis
kubectl -n kitabim logs deployment/redis --tail=200 -f
```

### Status

```bash
kubectl -n kitabim get pods
kubectl -n kitabim get svc
```

### Port-Forward (Backend)

```bash
kubectl -n kitabim port-forward svc/backend 8000:8000
```

### Health Checks

```bash
curl -s http://localhost:8000/health
curl -s http://localhost:8000/ready
```

### Tests

```bash
npm test
```

```bash
python3.13 -m pytest services/backend/tests
```

### Troubleshooting

- **docker-desktop context missing**: Enable Kubernetes in Docker Desktop (Settings → Kubernetes), then run `kubectl config get-contexts` and `kubectl config use-context docker-desktop`.
- **Pods stuck in Pending**: Check `infra/k8s/docker-desktop/pv.yaml` hostPath matches your repo path and that Docker Desktop has file sharing enabled for that path.
- **Backend not ready**: Confirm `kubectl -n kitabim get pods` and check logs with `kubectl -n kitabim logs deployment/backend`.

## Technology Stack

- **Frontend**: React 19, Vite 6, Tailwind (CDN), Lucide, pdf.js.
- **Backend**: FastAPI, MongoDB (Motor), PyMuPDF, LangChain, `langchain-google-genai`, `httpx`, `numpy`.
- **Queue/Worker**: Redis + ARQ.
- **Local OCR**: FastAPI, Tesseract, ONNX.
- **Local Dev**: Docker Desktop Kubernetes.
