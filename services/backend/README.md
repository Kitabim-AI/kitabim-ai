# Kitabim.AI Backend (LangChain)

## Setup
- Create `.env` at the repo root with the same variables as `.env.example`.
- Install dependencies:
  - `pip install -r services/backend/requirements.txt`

## Run (Dev)
- `uvicorn app.main:app --reload --port 8000 --app-dir services/backend`

## Notes
- Uses MongoDB from `MONGODB_URL` and the shared `data/` folder for uploads/covers.
- Override the data location with `DATA_DIR` (useful for Docker/K8s).
- If using local OCR, set `OCR_PROVIDER=local` and ensure `services/uyghurocr` is running on `LOCAL_OCR_URL`.
- API contract matches `docs/openapi.json`.
- LangChain-native chains/adapters live under `app/langchain`.
