import asyncio
import time
from fastapi import FastAPI, UploadFile, File, Query, HTTPException, status
from app.engine import run_ocr
from app.postprocess import postprocess_text

app = FastAPI(
    title="Kitabim EasyOCR Microservice",
    description="Self-hosted EasyOCR service optimized for Uyghur book transcriptions",
    version="1.0.0"
)


@app.on_event("startup")
async def startup_event():
    # Pre-load the EasyOCR reader for Uyghur so that requests have zero cold-start delay
    from app.engine import get_reader
    await asyncio.to_thread(get_reader, "ug")


@app.get("/health", status_code=status.HTTP_200_OK)
async def health():
    """Health check endpoint used by Docker orchestrators and checkers."""
    return {
        "status": "ok",
        "engine": "easyocr",
        "languages": ["ug"]
    }


@app.post("/ocr", status_code=status.HTTP_200_OK)
async def ocr(
    image: UploadFile = File(...),
    lang: str = Query("ug", description="EasyOCR Language Code"),
    paragraph: bool = Query(False, description="Combine lines into paragraphs inside EasyOCR"),
):
    """
    Accepts an uploaded page image (JPEG or PNG), performs deskewing/sharpening,
    runs EasyOCR, reconstructs spatial Markdown, applies spelling corrections,
    and returns the cleaned text.
    """
    # Validate image upload
    if not image or not image.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Missing required image file upload."
        )

    start_time = time.perf_counter()

    try:
        img_bytes = await image.read()
        
        # Offload CPU-heavy image processing and OCR execution to thread pool
        result = await asyncio.to_thread(run_ocr, img_bytes, lang, paragraph)
        
        # Post-process the extracted structural text (Unicode normalization, substitutions, cleanup)
        final_text = postprocess_text(result["text"])
        
        processing_time_ms = int((time.perf_counter() - start_time) * 1000)
        
        return {
            "text": final_text,
            "confidence": result["confidence"],
            "processing_time_ms": processing_time_ms
        }
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(val_err)
        )
    except Exception as exc:
        # Log or bubble up EasyOCR engine failures
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"EasyOCR Processing failed: {str(exc)}"
        )
