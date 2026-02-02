from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
import os
import shutil
import tempfile
from enum import Enum
from typing import Optional
from logic.ocr_processor import OcrProcessor
from logic.pdf_processor import PdfProcessor
from pydantic import BaseModel

# Optimization: Limit internal Tesseract threading to allow our parallel line logic to work better
os.environ["OMP_THREAD_LIMIT"] = "1"

class LangEnum(str, Enum):
    ukij = "ukij"
    uig = "uig"
    eng = "eng"
    rus = "rus"
    tur = "tur"
    chi_sim = "chi_sim"

class ModeEnum(str, Enum):
    auto = "auto"
    single = "single"
    line = "line"

app = FastAPI(title="UyghurOCR API (Python)")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TESSDATA_PATH = os.path.join(BASE_DIR, "tessdata")
MODEL_PATH = os.path.join(BASE_DIR, "model.onnx")

# Health/ready endpoints for local dev + k8s probes
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    tess_ok = os.path.isdir(TESSDATA_PATH)
    model_ok = os.path.exists(MODEL_PATH)
    if not tess_ok or not model_ok:
        raise HTTPException(
            status_code=503,
            detail={
                "tessdata_ok": tess_ok,
                "model_ok": model_ok,
            },
        )
    return {"status": "ready"}

# Initialize Processors
ocr_processor = OcrProcessor(TESSDATA_PATH, MODEL_PATH)
pdf_processor = PdfProcessor()

class OcrResponse(BaseModel):
    text: str

class PdfInfoResponse(BaseModel):
    page_count: int
    temp_id: str

@app.post("/api/ocr/pdf-info", response_model=PdfInfoResponse)
async def get_pdf_info(file: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(file.file, tmp)
        temp_path = tmp.name
    
    try:
        import fitz
        doc = fitz.open(temp_path)
        page_count = len(doc)
        doc.close()
        return {"page_count": page_count, "temp_id": os.path.basename(temp_path)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/api/ocr/pdf-page")
async def get_pdf_page(file: UploadFile = File(...), page: int = Form(0)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(file.file, tmp)
        temp_path = tmp.name
    
    try:
        img_bytes = pdf_processor.render_page_to_bytes(temp_path, page)
        if img_bytes is None:
            raise HTTPException(status_code=404, detail="Page not found")
        return Response(content=img_bytes, media_type="image/png")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/api/ocr/recognize", response_model=OcrResponse)
def recognize(
    file: UploadFile = File(...),
    lang: LangEnum = Form(LangEnum.ukij),
    mode: ModeEnum = Form(ModeEnum.auto),
    x: int = Form(0),
    y: int = Form(0),
    width: int = Form(0),
    height: int = Form(0),
    book_name: Optional[str] = Form(None),
    page_num: Optional[int] = Form(None)
):
    try:
        print(f"📖 OCR Request: Book={book_name or 'Unknown'}, Page={page_num or 'Unknown'}, Mode={mode.value}")
        image_bytes = file.file.read()
        roi = (x, y, width, height)
        result = ocr_processor.perform_ocr(image_bytes, lang.value, mode.value, roi)
        print(f"✅ OCR Success: Book={book_name or 'Unknown'}, Page={page_num or 'Unknown'}")
        return {"text": result}
    except Exception as e:
        print(f"❌ OCR Failure: Book={book_name or 'Unknown'}, Page={page_num or 'Unknown'}, Error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ocr/recognize-pdf", response_model=OcrResponse)
async def recognize_pdf(
    file: UploadFile = File(...),
    page: int = Form(0, description="Page index (0-based). Use -1 to recognize the whole book."),
    lang: LangEnum = Form(LangEnum.ukij),
    mode: ModeEnum = Form(ModeEnum.auto),
    book_name: Optional[str] = Form(None)
):
    print(f"📖 PDF OCR Request: Book={book_name or file.filename}, Page={page}, Mode={mode.value}")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        shutil.copyfileobj(file.file, tmp)
        temp_path = tmp.name
    
    try:
        if page == -1:
            # Process the whole book
            images = pdf_processor.render_pages(temp_path)
            full_text = []
            for img_bytes in images:
                page_text = ocr_processor.perform_ocr(img_bytes, lang.value, mode.value, (0, 0, 0, 0))
                full_text.append(page_text)
            
            print(f"✅ PDF OCR Success (Whole Book): Book={book_name or file.filename}")
            return {"text": "\n\f\n".join(full_text)}
        else:
            # Process a single page
            image_bytes = pdf_processor.render_page_to_bytes(temp_path, page)
            if image_bytes is None:
                raise HTTPException(status_code=404, detail="Page not found")
            
            result = ocr_processor.perform_ocr(image_bytes, lang.value, mode.value, (0, 0, 0, 0))
            print(f"✅ PDF OCR Success: Book={book_name or file.filename}, Page={page}")
            return {"text": result}
    except HTTPException:
        print(f"❌ PDF OCR Error: Book={book_name or file.filename}, Page={page}, Error=HTTPException")
        raise
    except Exception as e:
        print(f"❌ PDF OCR Failure: Book={book_name or file.filename}, Page={page}, Error={str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
