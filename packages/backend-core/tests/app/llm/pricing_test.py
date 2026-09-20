"""Unit tests for LLM pricing and cost estimation module."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.llm.pricing import (
    ModelPrice,
    DEFAULT_MODEL_PRICING,
    _FALLBACK_PRICE,
    parse_model_pricing,
    get_model_price,
    estimate_cost_usd,
    get_model_pricing_from_repo,
)
from app.llm.cost_tracker import CostTracker


def test_default_pricing_table_contains_expected_models():
    assert "gemini-3.1-flash-lite" in DEFAULT_MODEL_PRICING
    assert "gemini-3.7-flash" in DEFAULT_MODEL_PRICING
    assert "gemini-embedding-2" in DEFAULT_MODEL_PRICING
    assert DEFAULT_MODEL_PRICING["gemini-embedding-2"].output_per_million == 0.0


def test_parse_model_pricing_empty_or_none():
    pricing, fallback = parse_model_pricing(None)
    assert pricing == DEFAULT_MODEL_PRICING
    assert fallback == _FALLBACK_PRICE

    pricing, fallback = parse_model_pricing("")
    assert pricing == DEFAULT_MODEL_PRICING
    assert fallback == _FALLBACK_PRICE


def test_parse_model_pricing_valid_json():
    raw = json.dumps(
        {
            "gemini-custom": {"input": 0.50, "output": 1.50},
            "gemini-long": {"input_per_million": 2.0, "output_per_million": 5.0},
            "_fallback": {"input": 0.20, "output": 0.80},
        }
    )
    pricing, fallback = parse_model_pricing(raw)
    assert pricing["gemini-custom"] == ModelPrice(0.50, 1.50)
    assert pricing["gemini-long"] == ModelPrice(2.0, 5.0)
    assert fallback == ModelPrice(0.20, 0.80)
    # Merges on top of defaults
    assert "gemini-3.1-flash-lite" in pricing


def test_parse_model_pricing_invalid_json():
    pricing, fallback = parse_model_pricing("not valid json")
    assert pricing == DEFAULT_MODEL_PRICING
    assert fallback == _FALLBACK_PRICE


def test_get_model_price_with_and_without_custom_map():
    # Without custom map (defaults)
    price = get_model_price("gemini-3.1-flash-lite")
    assert price == DEFAULT_MODEL_PRICING["gemini-3.1-flash-lite"]

    # Strips models/ prefix
    price_prefixed = get_model_price("models/gemini-3.1-flash-lite")
    assert price_prefixed == price

    # Unknown model with default fallback
    unknown = get_model_price("unknown-model")
    assert unknown == _FALLBACK_PRICE

    # With custom map and custom fallback
    custom_map = {"custom-model": ModelPrice(0.05, 0.15)}
    custom_fallback = ModelPrice(1.0, 2.0)

    assert get_model_price("custom-model", custom_map) == ModelPrice(0.05, 0.15)
    assert (
        get_model_price("unknown", custom_map, fallback_price=custom_fallback)
        == custom_fallback
    )


def test_estimate_cost_usd():
    # 1M input + 1M output on gemini-3.1-flash-lite ($0.10 in / $0.40 out) = $0.50
    cost = estimate_cost_usd("gemini-3.1-flash-lite", 1_000_000, 1_000_000)
    assert round(cost, 4) == 0.50

    # With custom pricing map
    custom_map = {"gemini-3.1-flash-lite": ModelPrice(0.20, 0.80)}
    cost_custom = estimate_cost_usd(
        "gemini-3.1-flash-lite", 1_000_000, 1_000_000, pricing_map=custom_map
    )
    assert round(cost_custom, 4) == 1.00


@pytest.mark.asyncio
async def test_get_model_pricing_from_repo():
    mock_repo = MagicMock()
    mock_repo.get_value = AsyncMock(
        return_value=json.dumps(
            {
                "gemini-future": {"input": 0.12, "output": 0.45},
                "_fallback": {"input": 0.25, "output": 1.00},
            }
        )
    )

    pricing, fallback = await get_model_pricing_from_repo(mock_repo)
    assert pricing["gemini-future"] == ModelPrice(0.12, 0.45)
    assert fallback == ModelPrice(0.25, 1.00)
    mock_repo.get_value.assert_called_once_with("sys_llm_model_pricing")


def test_cost_tracker_dynamic_pricing():
    tracker = CostTracker()
    tracker.add("chat", "gemini-3.1-flash-lite", 1_000_000, 1_000_000)

    # Default cost: 0.10 + 0.40 = 0.50
    assert tracker.as_dict()["cost_usd"] == 0.50

    # Custom pricing map passed to as_dict
    custom_map = {"gemini-3.1-flash-lite": ModelPrice(0.20, 0.80)}
    assert tracker.as_dict(pricing_map=custom_map)["cost_usd"] == 1.00

    # Or set directly on tracker
    tracker.set_pricing(custom_map)
    assert tracker.as_dict()["cost_usd"] == 1.00
