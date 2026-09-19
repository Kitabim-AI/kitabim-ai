"""Gemini pricing table and dynamic loader for LLM cost estimation.

Prices are $ per 1M tokens, sourced from https://ai.google.dev/gemini-api/docs/pricing
at authoring time. Real-time rates can be configured dynamically via the
'sys_llm_model_pricing' system_configs key without requiring code redeployments.

DEFAULT_MODEL_PRICING and _FALLBACK_PRICE act as the baseline fallback if
database or Redis configurations are unavailable.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from app.db.repositories.system_configs_repository import SystemConfigsRepository

logger = logging.getLogger("app.llm.pricing")


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: float
    output_per_million: float


DEFAULT_MODEL_PRICING: dict[str, ModelPrice] = {
    "gemini-2.5-flash": ModelPrice(input_per_million=0.30, output_per_million=2.50),
    "gemini-2.5-flash-lite": ModelPrice(
        input_per_million=0.10, output_per_million=0.40
    ),
    "gemini-2.5-pro": ModelPrice(input_per_million=1.25, output_per_million=10.00),
    "gemini-3.1-flash-lite": ModelPrice(
        input_per_million=0.10, output_per_million=0.40
    ),
    "gemini-3.5-flash-lite": ModelPrice(
        input_per_million=0.10, output_per_million=0.40
    ),
    "gemini-3.7-flash": ModelPrice(input_per_million=0.30, output_per_million=2.50),
    "gemini-embedding-2": ModelPrice(input_per_million=0.15, output_per_million=0.0),
}

# Used when a model name isn't recognized.
# Priced at the current default chat model's rate so an unrecognized model
# doesn't silently show as free.
_FALLBACK_PRICE = ModelPrice(input_per_million=0.30, output_per_million=2.50)


def parse_model_pricing(
    raw: Any,
) -> tuple[dict[str, ModelPrice], ModelPrice]:
    """Parse JSON or dict into a model pricing map and fallback price.

    Merges on top of DEFAULT_MODEL_PRICING so any unspecified model still
    has a reasonable rate. If parsing fails, cleanly falls back to
    (DEFAULT_MODEL_PRICING, _FALLBACK_PRICE).
    """
    if not raw:
        return DEFAULT_MODEL_PRICING, _FALLBACK_PRICE

    parsed: dict = {}
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception as err:
            logger.warning("Failed to parse sys_llm_model_pricing JSON: %s", err)
            return DEFAULT_MODEL_PRICING, _FALLBACK_PRICE
    elif isinstance(raw, dict):
        parsed = raw

    if not isinstance(parsed, dict):
        return DEFAULT_MODEL_PRICING, _FALLBACK_PRICE

    pricing_map = dict(DEFAULT_MODEL_PRICING)
    fallback_price = _FALLBACK_PRICE

    for key, val in parsed.items():
        if not isinstance(val, dict):
            continue

        model_name = key.replace("models/", "", 1) if key.startswith("models/") else key
        inp = val.get("input") if "input" in val else val.get("input_per_million", 0.0)
        out = (
            val.get("output") if "output" in val else val.get("output_per_million", 0.0)
        )

        try:
            price = ModelPrice(
                input_per_million=float(inp),
                output_per_million=float(out),
            )
        except (ValueError, TypeError):
            continue

        if model_name in ("_fallback", "fallback"):
            fallback_price = price
        else:
            pricing_map[model_name] = price

    return pricing_map, fallback_price


async def get_model_pricing_from_repo(
    repo: SystemConfigsRepository,
) -> tuple[dict[str, ModelPrice], ModelPrice]:
    """Fetch model pricing configuration from system_configs (cached via Redis)."""
    try:
        raw_config = await repo.get_value("sys_llm_model_pricing")
        return parse_model_pricing(raw_config)
    except Exception as err:
        logger.warning(
            "Failed to fetch sys_llm_model_pricing from repository: %s. Using defaults.",
            err,
        )
        return DEFAULT_MODEL_PRICING, _FALLBACK_PRICE


def get_model_price(
    model: str,
    pricing_map: Optional[dict[str, ModelPrice]] = None,
    fallback_price: Optional[ModelPrice] = None,
) -> ModelPrice:
    """Resolve ModelPrice for a model name, stripping 'models/' prefix."""
    model = model.replace("models/", "", 1) if model.startswith("models/") else model
    active_map = pricing_map if pricing_map is not None else DEFAULT_MODEL_PRICING
    active_fallback = fallback_price if fallback_price is not None else _FALLBACK_PRICE
    return active_map.get(model, active_fallback)


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    pricing_map: Optional[dict[str, ModelPrice]] = None,
    fallback_price: Optional[ModelPrice] = None,
) -> float:
    """Calculate USD cost for input/output token counts."""
    price = get_model_price(
        model, pricing_map=pricing_map, fallback_price=fallback_price
    )
    return (input_tokens / 1_000_000) * price.input_per_million + (
        output_tokens / 1_000_000
    ) * price.output_per_million
