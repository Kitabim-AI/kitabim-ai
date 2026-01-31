# AGENTS.md — UyghurOCR

## Service Purpose
Local OCR API service (FastAPI) used when `OCR_PROVIDER=local`.

## Run (Dev)
```bash
python3.13 -m venv venv
source venv/bin/activate
pip install -r services/uyghurocr/requirements.txt
python3.13 services/uyghurocr/main.py
```

## Dependencies
- Tesseract + `tessdata/`
- `model.onnx` in this service directory

## Notes
- The backend calls this service via `LOCAL_OCR_URL`.
- Local dev uses Docker Desktop Kubernetes (see `infra/k8s/docker-desktop`).
