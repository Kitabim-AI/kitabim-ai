# UyghurOCR API

Local OCR service for Uyghur (and a few other languages) used by the Kitabim.AI backend when `OCR_PROVIDER=local`.

## Setup

```bash
python3.13 -m venv venv
source venv/bin/activate
pip install -r services/uyghurocr/requirements.txt
```

## Run

```bash
python3.13 services/uyghurocr/main.py
```

The API listens on `http://localhost:8001` by default.

## Endpoints

- `POST /api/ocr/recognize`
  - Multipart form fields:
    - `file`: image file (required)
    - `lang`: `ukij` | `uig` | `eng` | `rus` | `tur` | `chi_sim`
    - `mode`: `auto` | `single` | `line`
    - `x`, `y`, `width`, `height`: optional ROI crop (ints)
    - `book_name`, `page_num`: optional metadata
  - Response: `{ "text": "..." }`

- `POST /api/ocr/pdf-info`
  - Multipart form field: `file` (PDF)
  - Response: `{ "page_count": number, "temp_id": "..." }`

- `POST /api/ocr/pdf-page`
  - Multipart form fields: `file` (PDF), `page` (0-based)
  - Response: PNG image bytes

- `POST /api/ocr/recognize-pdf`
  - Multipart form fields: `file` (PDF), `page` (0-based, `-1` for full document), `lang`, `mode`, `book_name`
  - Response: `{ "text": "..." }`

## Notes

- The service uses `tessdata/` and `model.onnx` in this folder.
- The Kitabim.AI backend calls this service via `LOCAL_OCR_URL`.
- If you want the backend to use this service, set `OCR_PROVIDER=local` in the repo root `.env`.
