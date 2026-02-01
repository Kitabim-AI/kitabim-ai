import os
import cv2
import numpy as np
import pytesseract
from PIL import Image
import math
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
        os.environ["TESSDATA_PREFIX"] = os.path.abspath(tessdata_path)

    def deskew(self, img: np.ndarray) -> np.ndarray:
        """
        deskew the image using a simple angle detection.
        Original app uses Leptonica Pix.Deskew(), here we approximate with OpenCV.
        """
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            gray = cv2.bitwise_not(gray)
            coords = np.column_stack(np.where(gray > 0))
            angle = cv2.minAreaRect(coords)[-1]
            
            # The cv2.minAreaRect returns values in range [-90, 0).
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle

            # If angle is too small, ignore
            if abs(angle) < 0.1:
                return img

            (h, w) = img.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            rotated = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            return rotated
        except Exception as e:
            print(f"Deskew failed: {e}")
            return img

    def get_rotate_crop_image(self, img: np.ndarray, points: np.ndarray) -> np.ndarray:
        """
        Warp the perspective of the text line defined by the 4 points polygon.
        """
        rect = points.astype("float32")
        # Ensure consistency of points order: TL, TR, BR, BL
        # The TextDetector.get_mini_boxes attempts to order them, but let's be safe or trust it.
        # We will trust the output of TextDetector logic for now which mimics C# app logic.
        
        (tl, tr, br, bl) = rect

        # Compute width of the new image
        widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
        widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
        maxWidth = max(int(widthA), int(widthB))

        # Compute height of the new image
        heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
        heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
        maxHeight = max(int(heightA), int(heightB))

        # Destination points
        dst = np.array([
            [0, 0],
            [maxWidth - 1, 0],
            [maxWidth - 1, maxHeight - 1],
            [0, maxHeight - 1]], dtype="float32")

        # Compute the perspective transform matrix
        M = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(img, M, (maxWidth, maxHeight))

        # If the height is too small or aspect ratio is weird, we might want to pad
        if maxHeight < 20: 
             # Pad vertically to help Tesseract
             warped = cv2.copyMakeBorder(warped, 5, 5, 5, 5, cv2.BORDER_CONSTANT, value=[255,255,255])
        
        return warped

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

        # Deskewing
        # In the original app, Deskew is performed on the whole image before processing.
        img = self.deskew(img)

        if mode == "line":
            return self.line_recognition(img, lang)
        else:
            # Page Seg Mode mapping
            psm = 3 # Default Auto
            if mode == "auto": psm = 3
            elif mode == "single": psm = 6 # Single block
            
            # Use custom tessdata and config
            custom_config = f'--tessdata-dir "{self.tessdata_path}" --oem 1 --psm {psm}'
            text = pytesseract.image_to_string(img, lang=lang, config=custom_config)
            return self.post_process(text)

    def line_recognition(self, img: np.ndarray, lang: str) -> str:
        if self.line_detector is None:
            self.line_detector = TextDetector(self.onnx_model_path)

        # Detect text lines
        boxes, _ = self.line_detector.detect(img)
        
        # Sort boxes by Y coordinate (top to bottom)
        # Using the center Y of the box for more robust sorting
        boxes.sort(key=lambda b: (np.min(b[:, 1]) + np.max(b[:, 1])) / 2)
        
        # PSM 13 (Raw line) to match reference UyghurOCR behavior
        custom_config = f'--tessdata-dir "{self.tessdata_path}" --oem 1 --psm 13'

        results = []
        for box in boxes:
            # Warp/Crop the text line
            line_img = self.get_rotate_crop_image(img, box)
            
            if line_img.shape[0] == 0 or line_img.shape[1] == 0:
                continue

            # Run Tesseract on the line
            line_text = pytesseract.image_to_string(line_img, lang=lang, config=custom_config)
            line_text = self.post_process(line_text).strip()
            if line_text:
                results.append((line_text, box))

        # Post-processing: Join lines with hyphen-aware merging and paragraph detection
        final_text = self.join_lines_smart(results, img.shape[1])
        return final_text

    def post_process(self, text: str) -> str:
        if not text:
            return ""
        # Match C# normalization: Replace "ی" with "ي" and "ه" with "ە"
        text = text.replace("ی", "ي").replace("ه", "ە")
        
        # Hyphen handling could happen here if we processed full text, 
        # but since we join lines later, simpler regex might be better on full text.
        return text

    def join_lines_smart(self, lines_with_boxes: List[Tuple[str, np.ndarray]], page_width: int) -> str:
        if not lines_with_boxes:
            return ""
        
        # Heuristic constants
        # Uyghur is RTL, so paragraph indentation is on the RIGHT (smaller max_x if we assume 0 is left)
        # However, usually images are scanned such that text is loosely centered.
        
        final_lines = []
        current_paragraph = ""
        
        for i, (text, box) in enumerate(lines_with_boxes):
            s = text.strip()
            if not s:
                continue
            
            # Box metrics
            min_x = np.min(box[:, 0])
            max_x = np.max(box[:, 0])
            line_width = max_x - min_x
            
            if not current_paragraph:
                current_paragraph = s
                continue
            
            # 1. Hyphen check (always merge)
            if current_paragraph.endswith(("-", "–", "—", "_")):
                current_paragraph = current_paragraph.rstrip(" -–—_") + s
                continue
            
            # 2. Paragraph break heuristics
            is_new_paragraph = False
            
            # Marker check (Sentence enders in Uyghur: . ؟ ! ؛)
            ends_with_sentence_marker = current_paragraph.strip().endswith((".", "!", "؟", "؛", "»"))
            
            # Line length check: If the previous line was significantly shorter than the average line width
            # We don't have average yet, but we can compare to the current line width or a threshold.
            if i > 0:
                prev_text, prev_box = lines_with_boxes[i-1]
                prev_width = np.max(prev_box[:, 0]) - np.min(prev_box[:, 0])
                # If previous line is much shorter than current line, it might be the end of a paragraph.
                if prev_width < line_width * 0.8 and ends_with_sentence_marker:
                    is_new_paragraph = True

            # Indentation check (RTL): 
            # In RTL books, paragraphs are often indented from the right.
            # So the max_x of the box will be less than the 'normal' right margin.
            # We can compare max_x of current line with the max_x of the previous line.
            if i > 0:
                prev_text, prev_box = lines_with_boxes[i-1]
                prev_max_x = np.max(prev_box[:, 0])
                # If current line starts significantly further to the left (smaller max_x) than previous line
                # it's likely a paragraph indentation.
                if max_x < prev_max_x - (page_width * 0.05):
                    is_new_paragraph = True

            if is_new_paragraph:
                final_lines.append(current_paragraph)
                current_paragraph = s
            else:
                # Merge into current paragraph with a space
                current_paragraph = current_paragraph.rstrip() + " " + s
                
        if current_paragraph:
            final_lines.append(current_paragraph)
            
        return "\n\n".join(final_lines)

    def __del__(self):
        pass
