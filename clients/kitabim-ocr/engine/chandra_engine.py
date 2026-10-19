from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    from PIL import Image

logger = logging.getLogger("kitabim_ocr_client.engine.chandra")


class ChandraPredictor:
    """Wrapper for Chandra OCR predictor (datalab-to/chandra-ocr-2)."""

    def __init__(
        self,
        method: str | None = None,
        model_checkpoint: str | None = None,
    ) -> None:
        try:
            from chandra.model import InferenceManager
            from chandra.settings import settings as chandra_settings
        except ImportError as err:
            raise ImportError(
                "Chandra OCR requires 'chandra-ocr[hf]'.\n"
                "Install it with: pip install 'chandra-ocr[hf]'"
            ) from err

        import os
        from engine.config import (
            get_chandra_method,
            get_chandra_min_image_dim,
            get_chandra_model_checkpoint,
            get_chandra_prompt_guidance,
            get_chandra_prompt_type,
            get_chandra_repetition_penalty,
            is_apple_silicon,
        )

        self.method = (method or get_chandra_method()).strip().lower()
        checkpoint = (model_checkpoint or get_chandra_model_checkpoint()).strip()
        self.prompt_type = get_chandra_prompt_type()
        self.prompt_guidance = get_chandra_prompt_guidance()
        self.repetition_penalty = get_chandra_repetition_penalty()
        self.min_image_dim = get_chandra_min_image_dim()

        if checkpoint and hasattr(chandra_settings, "MODEL_CHECKPOINT"):
            chandra_settings.MODEL_CHECKPOINT = checkpoint

        # On Apple Silicon macOS, accelerate's auto-device mapping incorrectly infers an 8GB
        # limit and offloads layers to disk, causing massive slowdowns and timeouts.
        # Explicitly configure MPS as the torch device and lift the high watermark.
        if is_apple_silicon():
            os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")
            if not os.environ.get("TORCH_DEVICE") and hasattr(
                chandra_settings, "TORCH_DEVICE"
            ):
                chandra_settings.TORCH_DEVICE = "mps"

        # Cap default max generation tokens to 4096 to prevent runaway loops on single pages
        if (
            hasattr(chandra_settings, "MAX_OUTPUT_TOKENS")
            and (chandra_settings.MAX_OUTPUT_TOKENS or 0) > 4096
        ):
            chandra_settings.MAX_OUTPUT_TOKENS = 4096

        logger.info(
            "Initializing Chandra InferenceManager (method='%s', model='%s', device='%s', prompt_type='%s', rep_penalty=%.2f)...",
            self.method,
            checkpoint,
            getattr(chandra_settings, "TORCH_DEVICE", None) or "auto",
            self.prompt_type,
            self.repetition_penalty,
        )
        self.manager = InferenceManager(method=self.method)

    def _prepare_image(self, image: "Image.Image") -> "Image.Image":
        """Upscale image if smaller than min_image_dim to ensure 28x28 patch clarity."""
        from PIL import Image as PILImage

        w, h = image.size
        min_dim = min(w, h)
        target_min = getattr(self, "min_image_dim", 1536)
        if min_dim > 0 and min_dim < target_min:
            scale = target_min / min_dim
            new_size = (int(round(w * scale)), int(round(h * scale)))
            return image.resize(new_size, PILImage.Resampling.LANCZOS)
        return image

    def _build_prompt(self) -> str:
        """Compose effective prompt by combining language guidance with base OCR instructions."""
        from chandra.prompts import PROMPT_MAPPING

        prompt_type = getattr(self, "prompt_type", "ocr_layout")
        guidance = getattr(self, "prompt_guidance", None)
        base_prompt = PROMPT_MAPPING.get(
            prompt_type, PROMPT_MAPPING.get("ocr_layout", "")
        )
        if guidance:
            return (
                f"{guidance.strip()}\n\n{base_prompt}"
                if base_prompt
                else guidance.strip()
            )
        return base_prompt

    def recognize_image(self, image: "Image.Image") -> Tuple[str, float]:
        """Run OCR on a PIL Image and return (markdown, confidence)."""
        from chandra.model.schema import BatchInputItem
        from chandra.settings import settings as chandra_settings

        processed_image = self._prepare_image(image)
        prompt = self._build_prompt()
        prompt_type = getattr(self, "prompt_type", "ocr_layout")
        rep_penalty = getattr(self, "repetition_penalty", 1.05)

        max_tokens = getattr(chandra_settings, "MAX_OUTPUT_TOKENS", 4096)
        item = BatchInputItem(
            image=processed_image,
            prompt=prompt,
            prompt_type=prompt_type,
        )

        gen_kwargs: dict = {
            "max_output_tokens": max_tokens,
        }
        if getattr(self, "method", "hf") == "hf":
            gen_kwargs["do_sample"] = False
            gen_kwargs["repetition_penalty"] = rep_penalty

        results = self.manager.generate([item], **gen_kwargs)
        if not results:
            return "", 0.0
        res = results[0]
        markdown = (res.markdown or "").strip()
        confidence = 1.0 if not res.error else 0.0
        return markdown, confidence
