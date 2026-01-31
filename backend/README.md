# Kitabim.AI Backend (LangChain)

## Setup
- Create `.env` at repo root (or in `backend`) with the same variables as `.env.example`.
- Install dependencies:
  - `pip install -r backend/requirements.txt`

## Run
- `uvicorn app.main:app --reload --port 8000 --app-dir backend`

## Notes
- Uses MongoDB from `MONGODB_URL` and the shared `data/` folder for uploads/covers.
- API contract matches `docs/openapi.json`.
- LangChain-native chains/adapters live under `app/langchain`.
