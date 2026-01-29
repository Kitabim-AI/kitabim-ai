# Kitabim.AI Backend v2 (LangChain)

## Setup
- Create `.env` at repo root (or in `backend-v2`) with the same variables as `.env.example`.
- Install dependencies:
  - `pip install -r backend-v2/requirements.txt`

## Run
- `uvicorn app.main:app --reload --port 8000 --app-dir backend-v2`

## Notes
- Uses MongoDB from `MONGODB_URL` and the shared `data/` folder for uploads/covers.
- API contract matches `docs/openapi.json`.
