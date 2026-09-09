"""
LLM Spell Check Service — on-demand, admin-triggered Gemini-based spell
correction for context-dependent real-word errors. Shared by the live worker
job path (llm_spell_check_job) and the Gemini Batch API path
(batch_llm_spell_check_service).
"""

from __future__ import annotations

from typing import Optional

from google.genai import types

from app.core.prompts import LLM_SPELL_CHECK_PROMPT
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.llm.models import build_text_llm

_MAX_LENGTH_DEVIATION_RATIO = 0.3


def build_correction_prompt(
    page_text: str, prev_page_text: Optional[str], next_page_text: Optional[str]
) -> str:
    return LLM_SPELL_CHECK_PROMPT.format(
        prev_context=prev_page_text or "",
        page_text=page_text,
        next_context=next_page_text or "",
    )


def _validate_correction(original: str, corrected: str) -> None:
    """Cheap sanity guardrail against catastrophic model failures (empty or
    wildly truncated/garbled output) — not a dictionary-based per-word check,
    which is deferred to Future Enhancements per the design doc. Shared by
    both the live path and the batch poller.
    """
    if not corrected or not corrected.strip():
        raise ValueError("LLM spell check returned empty output")

    original_len = len(original)
    if original_len == 0:
        return
    deviation = abs(len(corrected) - original_len) / original_len
    if deviation > _MAX_LENGTH_DEVIATION_RATIO:
        raise ValueError(
            f"LLM spell check output length deviates {deviation:.0%} from original "
            f"(original={original_len} chars, corrected={len(corrected)} chars)"
        )


async def correct_page_text(
    page_text: str,
    prev_page_text: Optional[str],
    next_page_text: Optional[str],
    config_repo: SystemConfigsRepository,
) -> str:
    """Live path — one synchronous generate_content call. Used for every
    per-page trigger, and for per-book triggers when
    llm_spell_check_batch_enabled is false.

    Uses build_text_llm/ProtectedLLM (not a raw genai.Client) so the call
    goes through the shared circuit breaker and rate limiter, per project
    convention for single-shot structured LLM calls.
    """
    model = await config_repo.get_value(
        "gemini_llm_spell_check_model", "gemini-3.1-flash-lite"
    )
    prompt = build_correction_prompt(page_text, prev_page_text, next_page_text)
    llm = build_text_llm(model)
    corrected = await llm.ainvoke(
        prompt, config=types.GenerateContentConfig(temperature=0.0)
    )
    corrected = corrected.strip()
    _validate_correction(page_text, corrected)
    return corrected
