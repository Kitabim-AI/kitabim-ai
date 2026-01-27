import os
import cv2
import numpy as np
import pytesseract
from PIL import Image
import io
from .text_detector import TextDetector
from typing import List, Tuple
from concurrent.futures import ThreadPoolExecutor

class OcrProcessor:
    def __init__(self, tessdata_path: str, onnx_model_path: str):
        self.tessdata_path = tessdata_path
        self.onnx_model_path = onnx_model_path
        self.line_detector = None
        self.executor = ThreadPoolExecutor(max_workers=os.cpu_count() or 4)
        # Configure tesseract for custom tessdata
        # Note: In python, we often set TESSDATA_PREFIX environment variable
        os.environ["TESSDATA_PREFIX"] = os.path.abspath(tessdata_path)

    def perform_ocr(self, image_bytes: bytes, lang: str, mode: str, roi: Tuple[int, int, int, int]) -> str:
        # Load image
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if img is None:
            return ""

        h, w = img.shape[:2]
        rx, ry, rw, rh = roi
        
        # ROI cropping
        if rw > 0 and rh > 0:
            x1, y1 = max(0, rx), max(0, ry)
            x2, y2 = min(w, rx + rw), min(h, ry + rh)
            if x2 > x1 and y2 > y1:
                img = img[y1:y2, x1:x2]

        # In Python/PyTesseract, DPI is often handled by the image resolution in metadata or via --dpi flag
        # Tesseract 4+ LSTM works best with 300 DPI.
        
        # Deskew logic (simple version or similar to C# Deskew but OpenCV approach)
        # For now, let's keep it simple as C# deskew was Pix.Deskew()
        
        if mode == "line":
            return self.line_recognition(img, lang)
        else:
            # Page Seg Mode mapping
            psm = 3 # Default Auto
            if mode == "auto": psm = 3
            elif mode == "single": psm = 6 # Single block
            
            # Use custom tessdata and config
            custom_config = f'--tessdata-dir "{self.tessdata_path}" --psm {psm}'
            text = pytesseract.image_to_string(img, lang=lang, config=custom_config)
            return self.post_process(text)

    def line_recognition(self, img: np.ndarray, lang: str) -> str:
        if self.line_detector is None:
            self.line_detector = TextDetector(self.onnx_model_path)

        org_h, org_w = img.shape[:2]
        boxes, _ = self.line_detector.detect(img)
        
        # Sort boxes by Y coordinate (top to bottom)
        boxes.sort(key=lambda b: np.min(b[:, 1]))
        
        custom_config = f'--tessdata-dir "{self.tessdata_path}" --psm 13' # PSM 13 = Raw Line

        def process_single_line(box):
            min_x = int(max(0, np.min(box[:, 0]) - 10))
            min_y = int(max(0, np.min(box[:, 1]) - 5))
            max_x = int(min(org_w, np.max(box[:, 0]) + 10))
            max_y = int(min(org_h, np.max(box[:, 1]) + 5))
            
            if max_x <= min_x or max_y <= min_y:
                return None
            
            line_img = img[min_y:max_y, min_x:max_x]
            line_text = pytesseract.image_to_string(line_img, lang=lang, config=custom_config)
            line_text = self.post_process(line_text).strip()
            return line_text if line_text else None

        # Process lines in parallel
        results = list(self.executor.map(process_single_line, boxes))
        
        # Filter out None and combine
        qurlar = [res for res in results if res is not None]
        return "\n".join(qurlar)

    def post_process(self, text: str) -> str:
        if not text:
            return ""
        # Match C# normalization: Replace "ی" with "ي" and "ه" with "ە"
        return text.replace("ی", "ي").replace("ه", "ە")

    def __del__(self):
        # Clean up if needed, though Python handles typical GC
        pass
