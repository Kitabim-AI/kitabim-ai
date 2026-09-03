from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from PIL import Image

logger = logging.getLogger("kitabim_ocr_client.engine.savitr")


def convert_surya_mlx_model(
    output_dir: str | None = None,
    hf_path: str = "datalab-to/surya-ocr-2",
    q_bits: int = 4,
) -> str:
    """Download and convert Surya base model from Hugging Face to MLX format."""
    try:
        from mlx_vlm import convert
    except ImportError as err:
        raise ImportError(
            "mlx-vlm is required to convert Surya models on Apple Silicon. "
            "Install with: pip install mlx-vlm"
        ) from err

    dest = output_dir or str(
        Path.home() / ".cache" / "savitr" / f"surya-mlx-{q_bits}bit"
    )
    dest_path = Path(dest).expanduser()
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("Converting %s to MLX format at %s...", hf_path, dest_path)
    convert(hf_path=hf_path, mlx_path=str(dest_path), quantize=True, q_bits=q_bits)
    logger.info("Conversion complete: %s", dest_path)
    return str(dest_path)


class SavitrPredictor:
    """Wrapper for Savitr MLX-accelerated Surya OCR predictor."""

    def __init__(
        self, model_path: str | None = None, auto_convert: bool = False
    ) -> None:
        try:
            from savitr.mlx_ocr import MLXSuryaOCR
        except ImportError:
            try:
                from savitr import MLXSuryaOCR
            except ImportError as err:
                raise ImportError(
                    "Savitr OCR requires the 'savitr' package on Apple Silicon.\n"
                    "Install it with: pip install savitr\n"
                    "Or ensure your environment has Apple Silicon (M-series) with MLX."
                ) from err

        try:
            self.engine = MLXSuryaOCR(mlx_path=model_path)
        except FileNotFoundError as err:
            if auto_convert:
                converted_path = convert_surya_mlx_model(output_dir=model_path)
                self.engine = MLXSuryaOCR(mlx_path=converted_path)
            else:
                logger.error("Savitr base model not found: %s", err)
                raise

    def recognize_image(self, image: "Image.Image") -> Tuple[str, float]:
        """Run OCR on a PIL Image and return (html_text, confidence)."""
        # If the engine supports _generate with PIL image directly:
        if hasattr(self.engine, "_generate") and hasattr(self.engine, "model"):
            try:
                res = self.engine._generate(
                    self.engine.model,
                    self.engine.processor,
                    self.engine.prompt,
                    image=image,
                    max_tokens=self.engine.max_tokens,
                    verbose=False,
                )
                text = getattr(res, "text", None) or str(res)
                return text, 1.0
            except Exception as e:
                logger.debug("Direct generate failed, falling back to temp file: %s", e)

        # Fallback to temp file via ocr_image:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            try:
                image.save(tmp_path, format="PNG")
                text, _ = self.engine.ocr_image(str(tmp_path))
                return text, 1.0
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
