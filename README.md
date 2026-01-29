# Kitabim.AI Monorepo

The intelligent Uyghur Digital Library platform for OCR, curation, and RAG-powered reading.

## Structure

- `/backend`: FastAPI API + background processing pipeline.
  - `app/api`: Book and chat endpoints.
  - `app/services`: PDF OCR, embeddings, spell check, and AI helpers.
  - `app/core`: Settings and prompts.
  - `app/db`: MongoDB connection and repositories.
  - `app/models`: Pydantic schemas.
  - `app/utils`: Text cleaning helpers.
- `/uyghurocr-api`: Local OCR service (FastAPI) using Tesseract + ONNX.
  - `logic`: OCR and PDF processing logic.
  - `tessdata`: Tesseract language data.
- `/frontend/src`: React UI.
  - `components`: Library, Reader, Admin, Chat, Spell Check, layout/common UI.
  - `hooks`: Global state and data fetching.
  - `services`: API clients and Gemini helpers.
- `/data`: Persistent storage created at runtime (ignored by git).
  - `uploads/`: Original PDF files.
  - `covers/`: Extracted book cover images.
- `/index.html`, `/index.tsx`, `/index.css`: Vite entry + global styles (Tailwind via CDN).
- `/vite.config.ts`: Vite config + API proxying to backend.

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
- **Python**: 3.9+
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
```

Notes:
- `GEMINI_API_KEY` is used by both the backend and the frontend (Vite injects it).
- Set `OCR_PROVIDER=local` to route OCR to the local OCR service.

### Backend Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
python3 backend/main.py
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
cd uyghurocr-api
source ../venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

Local OCR API runs on `http://localhost:8001` by default.

### Tests

```bash
npm test
```

```bash
python3 -m pytest backend/tests
```

## Technology Stack

- **Frontend**: React 19, Vite 6, Tailwind (CDN), Lucide, pdf.js, `@google/genai`.
- **Backend**: FastAPI, MongoDB (Motor), PyMuPDF, `google-genai`, `httpx`, `numpy`.
- **Local OCR**: FastAPI, Tesseract, ONNX.
