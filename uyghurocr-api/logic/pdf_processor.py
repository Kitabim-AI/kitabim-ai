import fitz  # PyMuPDF
from typing import List, Optional
import io

class PdfProcessor:
    def render_pages(self, pdf_path: str, dpi: int = 300) -> List[bytes]:
        images = []
        try:
            doc = fitz.open(pdf_path)
            for page in doc:
                # zoom factor
                zoom = dpi / 72  # 72 is default PDF resolution
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
                images.append(pix.tobytes("png"))
            doc.close()
        except Exception as e:
            print(f"Error rendering PDF: {e}")
        return images

    def render_page_to_bytes(self, pdf_path: str, page_index: int, dpi: int = 300) -> Optional[bytes]:
        try:
            doc = fitz.open(pdf_path)
            if page_index < 0 or page_index >= len(doc):
                doc.close()
                return None
            
            page = doc[page_index]
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)
            img_bytes = pix.tobytes("png")
            doc.close()
            return img_bytes
        except Exception as e:
            print(f"Error rendering PDF page: {e}")
            return None
