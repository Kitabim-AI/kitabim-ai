"""Per-turn LLM cost accumulator.

Attached to QueryContext.cost_tracker (see app/services/rag/context.py) so
any code holding — or able to fetch via get_current_query_context() — the
active turn's QueryContext can record usage without a new parameter
threaded through every call site between the orchestrator and the LLM call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.llm.pricing import ModelPrice, estimate_cost_usd


@dataclass
class CostEntry:
    stage: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated: bool = False
    pricing_map: Optional[dict[str, ModelPrice]] = None
    fallback_price: Optional[ModelPrice] = None

    @property
    def cost_usd(self) -> float:
        return estimate_cost_usd(
            self.model,
            self.input_tokens,
            self.output_tokens,
            pricing_map=self.pricing_map,
            fallback_price=self.fallback_price,
        )


@dataclass
class CostTracker:
    entries: list[CostEntry] = field(default_factory=list)
    pricing_map: Optional[dict[str, ModelPrice]] = None
    fallback_price: Optional[ModelPrice] = None

    def set_pricing(
        self,
        pricing_map: dict[str, ModelPrice],
        fallback_price: Optional[ModelPrice] = None,
    ) -> None:
        """Set dynamic model pricing map and fallback price for this tracker."""
        self.pricing_map = pricing_map
        self.fallback_price = fallback_price
        for entry in self.entries:
            entry.pricing_map = pricing_map
            entry.fallback_price = fallback_price

    def add(
        self,
        stage: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        estimated: bool = False,
    ) -> None:
        if input_tokens <= 0 and output_tokens <= 0:
            return
        self.entries.append(
            CostEntry(
                stage=stage,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated=estimated,
                pricing_map=self.pricing_map,
                fallback_price=self.fallback_price,
            )
        )

    @property
    def total_input_tokens(self) -> int:
        return sum(e.input_tokens for e in self.entries)

    @property
    def total_output_tokens(self) -> int:
        return sum(e.output_tokens for e in self.entries)

    def get_total_cost_usd(
        self,
        pricing_map: Optional[dict[str, ModelPrice]] = None,
        fallback_price: Optional[ModelPrice] = None,
    ) -> float:
        active_map = pricing_map if pricing_map is not None else self.pricing_map
        active_fallback = (
            fallback_price if fallback_price is not None else self.fallback_price
        )
        return sum(
            estimate_cost_usd(
                e.model,
                e.input_tokens,
                e.output_tokens,
                pricing_map=active_map,
                fallback_price=active_fallback,
            )
            for e in self.entries
        )

    @property
    def total_cost_usd(self) -> float:
        return self.get_total_cost_usd()

    def as_dict(
        self,
        pricing_map: Optional[dict[str, ModelPrice]] = None,
        fallback_price: Optional[ModelPrice] = None,
    ) -> dict:
        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "cost_usd": round(
                self.get_total_cost_usd(
                    pricing_map=pricing_map, fallback_price=fallback_price
                ),
                6,
            ),
        }
