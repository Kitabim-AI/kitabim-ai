"""Static Gemini pricing table for LLM cost estimation.

Prices are $ per 1M tokens, sourced from https://ai.google.dev/gemini-api/docs/pricing
at authoring time. Google revises model names and prices independently of
this file — treat the resulting cost figures as a best-effort estimate for
trend/eval purposes, not a billing-grade reconciliation. Update this table
when a model used by the chat pipeline (rag_gemini_chat_model,
gemini_agent_loop_model, rag_gemini_reranker_model, rag_gemini_judge_model,
embed_gemini_model system_configs) changes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: float
    output_per_million: float


MODEL_PRICING: dict[str, ModelPrice] = {
    "gemini-2.5-flash": ModelPrice(input_per_million=0.30, output_per_million=2.50),
    "gemini-2.5-flash-lite": ModelPrice(
        input_per_million=0.10, output_per_million=0.40
    ),
    "gemini-2.5-pro": ModelPrice(input_per_million=1.25, output_per_million=10.00),
    "gemini-3.1-flash-lite": ModelPrice(
        input_per_million=0.10, output_per_million=0.40
    ),
    "gemini-3.7-flash": ModelPrice(input_per_million=0.30, output_per_million=2.50),
    "gemini-embedding-2": ModelPrice(input_per_million=0.15, output_per_million=0.0),
}

# Used when a configured model name isn't in the table above (e.g. a
# system_configs value was updated to a newer model before this table was).
# Priced at the current default chat model's rate so an unrecognized model
# doesn't silently show as free.
_FALLBACK_PRICE = ModelPrice(input_per_million=0.30, output_per_million=2.50)


def get_model_price(model: str) -> ModelPrice:
    model = model.replace("models/", "", 1) if model.startswith("models/") else model
    return MODEL_PRICING.get(model, _FALLBACK_PRICE)


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    price = get_model_price(model)
    return (input_tokens / 1_000_000) * price.input_per_million + (
        output_tokens / 1_000_000
    ) * price.output_per_million
