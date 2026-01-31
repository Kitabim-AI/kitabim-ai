# Kitabim.AI Monorepo

The intelligent Uyghur Digital Library platform for OCR, curation, and RAG-powered reading.

## Structure

- `/services/backend`: FastAPI API + background processing pipeline.
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
- `/apps/frontend`: React UI (Vite).
  - `src/components`: Library, Reader, Admin, Chat, Spell Check, layout/common UI.
  - `src/hooks`: Global state and data fetching.
  - `src/services`: API clients and Gemini helpers.
- `/packages/shared`: Shared TS types/utilities.
- `/data`: Persistent storage created at runtime (ignored by git).
  - `uploads/`: Original PDF files.
  - `covers/`: Extracted book cover images.
- `/infra/k8s/kind`: Kind cluster config + manifests.

## Core Features

- **SHA-256 deduplication** to avoid re-processing identical PDFs.
- **Parallel OCR pipeline** with resumable tasks, cover extraction, and batch embeddings.
- **Gemini or local OCR** (switchable via `OCR_PROVIDER`).
- **RAG chat** per book or global, with work-aware context and citations by page.
- **Spell check & correction workflow** for OCR cleanup and embedding regeneration.
- **Admin tools** for reprocessing, deletion, author/volume/category edits, and cover uploads.
- **RTL reader** with inline page editing and page-level reprocess.

## Local Development

### Prerequisites

- **Node.js**: v18+
- **Python**: 3.13 (required)
- **MongoDB**: `mongodb://localhost:27017`

### Environment Variables

Create a `.env` file in the repo root:

```env
GEMINI_API_KEY=your_google_gemini_api_key
GEMINI_MODEL_NAME=gemini-3-flash-preview
GEMINI_CATEGORIZATION_MODEL=gemini-3-flash-preview
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001
MONGODB_URL=mongodb://localhost:27017
MAX_PARALLEL_PAGES=1
OCR_PROVIDER=gemini
LOCAL_OCR_URL=http://localhost:8001
DATA_DIR=./data
```

Notes:
- `GEMINI_API_KEY` is used by both the backend and the frontend (Vite injects it).
- Set `OCR_PROVIDER=local` to route OCR to the local OCR service.

### Dev Quickstart (Local)

From the repo root, run these in separate terminals:

```bash
# Terminal 1: MongoDB (if not already running)
mongod --dbpath /path/to/mongo/data
```

```bash
# Terminal 2: UyghurOCR (only needed if OCR_PROVIDER=local)
python3.13 -m venv venv
source venv/bin/activate
pip install -r services/uyghurocr/requirements.txt
python3.13 services/uyghurocr/main.py
```

```bash
# Terminal 3: Backend API
source venv/bin/activate
pip install -r services/backend/requirements.txt
uvicorn app.main:app --reload --port 8000 --app-dir services/backend
```

```bash
# Terminal 4: Frontend UI
npm install
npm run dev
```

Frontend runs on `http://localhost:3000` (proxying `/api` to the backend).

### Backend Setup

```bash
python3.13 -m venv venv
source venv/bin/activate
pip install -r services/backend/requirements.txt
uvicorn app.main:app --reload --port 8000 --app-dir services/backend
```

Backend runs on `http://localhost:8000`.

### Frontend Setup

```bash
npm install
npm run dev
```

Frontend runs on `http://localhost:3000` (Vite proxies `/api` to the backend).

### Local OCR API (Optional)

```bash
cd services/uyghurocr
source ../venv/bin/activate
pip install -r requirements.txt
python3.13 main.py
```

Local OCR API runs on `http://localhost:8001` by default.

### Tests

```bash
npm test
```

```bash
python3.13 -m pytest services/backend/tests
```

## Docker (Compose)

```bash
docker compose up --build
```

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- UyghurOCR: `http://localhost:8001`

## Kubernetes (kind)

1. Update `infra/k8s/kind/cluster.yaml` if your repo path differs (for the shared `/data` mount).
2. Create the cluster:

```bash
kind create cluster --config infra/k8s/kind/cluster.yaml
```

3. Build and load images into kind:

```bash
docker build -t kitabim-backend:local services/backend
docker build -t kitabim-uyghurocr:local services/uyghurocr
docker build -t kitabim-frontend:local -f apps/frontend/Dockerfile . --build-arg GEMINI_API_KEY=$GEMINI_API_KEY
kind load docker-image kitabim-backend:local kitabim-uyghurocr:local kitabim-frontend:local
```

4. Apply manifests:

```bash
kubectl apply -k infra/k8s/kind
```

5. Update `infra/k8s/kind/secret.yaml` with your `GEMINI_API_KEY` and re-apply if needed.
6. Access services:
   - Frontend: `http://localhost:30080`
   - Backend: `kubectl -n kitabim port-forward svc/backend 8000:8000`

## Technology Stack

- **Frontend**: React 19, Vite 6, Tailwind (CDN), Lucide, pdf.js, `@google/genai`.
- **Backend**: FastAPI, MongoDB (Motor), PyMuPDF, LangChain, `google-genai`, `httpx`, `numpy`.
- **Local OCR**: FastAPI, Tesseract, ONNX.
