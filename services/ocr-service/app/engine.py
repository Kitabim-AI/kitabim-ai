import cv2
import numpy as np
import easyocr
import os
import torch
from app.structure import analyze_layout

# Configure PyTorch CPU threads (default to 4, configurable via environment variable)
num_threads = int(os.environ.get("OCR_NUM_THREADS", "4"))
torch.set_num_threads(num_threads)

# Bounded cache for readers to avoid reloading weights on every request
_readers = {}


def get_reader(lang: str) -> easyocr.Reader:
    """Normalize language code and return a cached EasyOCR Reader instance."""
    normalized_lang = "ug" if lang in ("uig", "ug", "ukij") else lang
    if normalized_lang not in _readers:
        # Initialize reader on CPU (Docker runs CPU by default)
        _readers[normalized_lang] = easyocr.Reader([normalized_lang], gpu=False)
    return _readers[normalized_lang]


def resize_image_max_dim(img: np.ndarray, max_dim: int = 1000) -> np.ndarray:
    """Resize image to a maximum dimension to prevent PyTorch OOM crashes on CPU."""
    h, w = img.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        new_w = int(w * scale)
        new_h = int(h * scale)
        return cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    return img


def deskew_image(image_gray: np.ndarray) -> np.ndarray:
    """
    Calculate the skew angle and rotate the grayscale image.
    Uses Otsu thresholding on a temporary copy for angle computation,
    but applies the rotation matrix directly to the source grayscale image
    to preserve anti-aliased character edges.
    """
    # Threshold the image to isolate text contours
    _, thresh = cv2.threshold(image_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Get all coordinates of text pixels
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) == 0:
        return image_gray
        
    # Get the minimum bounding box around text coords
    angle = cv2.minAreaRect(coords)[-1]
    
    # Map angle to the range [-45, 45] degrees
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
        
    # Rotate only if skew is significant but within reasonable scan limits
    if abs(angle) > 0.5 and abs(angle) < 45:
        (h, w) = image_gray.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            image_gray, M, (w, h), 
            flags=cv2.INTER_CUBIC, 
            borderMode=cv2.BORDER_REPLICATE
        )
        return rotated
    return image_gray


def preprocess_image(img_bytes: bytes) -> np.ndarray:
    """Decode JPEG/PNG bytes and apply grayscale, resizing, deskew, and sharpening filters."""
    # 1. Decode bytes directly to grayscale
    nparr = np.frombuffer(img_bytes, np.uint8)
    gray = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError("Invalid image bytes provided. Could not decode image.")

    # 2. Resize to a safe maximum dimension to prevent PyTorch OOM crashes on CPU
    resized = resize_image_max_dim(gray, max_dim=1000)

    # 3. Apply deskewing
    deskewed = deskew_image(resized)

    # 4. Apply mild Unsharp Mask sharpening to improve character edge definitions
    gaussian = cv2.GaussianBlur(deskewed, (5, 5), 0)
    sharpened = cv2.addWeighted(deskewed, 1.5, gaussian, -0.5, 0)

    return sharpened


def run_ocr(img_bytes: bytes, lang: str = "ug", paragraph: bool = False) -> dict:
    """
    Preprocess image, execute EasyOCR, calculate confidence,
    and reconstruct spatial Markdown layout.
    """
    # Preprocess image
    processed_img = preprocess_image(img_bytes)
    h, w = processed_img.shape[:2]

    # Get the cached EasyOCR reader
    reader = get_reader(lang)

    # Run EasyOCR with detail=1 to get word-level bounding boxes and confidence scores
    ocr_results = reader.readtext(processed_img, paragraph=paragraph, detail=1)

    # Calculate average confidence
    conf_scores = [float(res[2]) for res in ocr_results]
    mean_conf = float(np.mean(conf_scores)) if conf_scores else 0.0

    # Build Markdown layout structure using spatial heuristics
    structured_text = analyze_layout(ocr_results, w, h)

    return {
        "text": structured_text,
        "confidence": round(mean_conf, 4)
    }
