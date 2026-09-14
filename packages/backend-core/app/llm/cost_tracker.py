"""Per-turn LLM cost accumulator.

Attached to QueryContext.cost_tracker (see app/services/rag/context.py) so
any code holding — or able to fetch via get_current_query_context() — the
active turn's QueryContext can record usage without a new parameter
threaded through every call site between the orchestrator and the LLM call.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.llm.pricing import estimate_cost_usd


@dataclass
class CostEntry:
    stage: str
    model: str
    input_tokens: int
    output_tokens: int
    estimated: bool = False

    @property
    def cost_usd(self) -> float:
        return estimate_cost_usd(self.model, self.input_tokens, self.output_tokens)


@dataclass
class CostTracker:
    entries: list[CostEntry] = field(default_factory=list)

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
            )
        )

    @property
    def total_input_tokens(self) -> int:
        return sum(e.input_tokens for e in self.entries)

    @property
    def total_output_tokens(self) -> int:
        return sum(e.output_tokens for e in self.entries)

    @property
    def total_cost_usd(self) -> float:
        return sum(e.cost_usd for e in self.entries)

    def as_dict(self) -> dict:
        return {
            "input_tokens": self.total_input_tokens,
            "output_tokens": self.total_output_tokens,
            "cost_usd": round(self.total_cost_usd, 6),
        }
