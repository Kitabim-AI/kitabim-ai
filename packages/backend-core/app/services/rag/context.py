"""QueryContext — per-request state threaded through ChatOrchestrator's tool calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from contextvars import ContextVar
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.db.models import Book

_current_query_context: ContextVar[Optional[QueryContext]] = ContextVar(
    "current_query_context", default=None
)


def set_current_query_context(ctx: QueryContext) -> None:
    _current_query_context.set(ctx)


def get_current_query_context() -> Optional[QueryContext]:
    return _current_query_context.get()


@dataclass
class QueryContext:
    # ── From ChatRequest ────────────────────────────────────────────────────
    session: "AsyncSession"
    question: str
    book_id: str
    is_global: bool
    current_page: Optional[int]
    character_id: str
    user_id: Optional[str]
    history: List[dict]

    # ── Resolved at facade entry (_build_context) ───────────────────────────
    book: Optional["Book"]  # None when is_global=True
    persona_prompt: Optional[str]
    character_categories: List[str]
    chat_history_str: str
    rag_chain: object
    rewrite_chain: object
    embeddings: object
    start_ts: float
    agent_model: str  # gemini_agent_loop_model → gemini_chat_model

    # ── Mutated by handlers ─────────────────────────────────────────────────
    query_vector: List[float] = field(default_factory=list)
    enriched_question: Optional[str] = (
        None  # QueryRewriter rewrites follow-up question here
    )
    context_book_ids: List[str] = field(
        default_factory=list
    )  # from ChatRequest — reliable frontend-tracked context
    used_book_ids: List[str] = field(
        default_factory=list
    )  # populated by retrieval, returned in done event

    # ── Eval metadata. Set by the deleted legacy pipeline's `_build_context`/
    # `_record_eval`; `ChatOrchestrator` computes its `rag_evaluations` insert
    # from local variables directly instead of reading these back — dead
    # fields, nothing sets or reads them today. ─────────────────────────────
    retrieved_count: int = 0
    context_chars: int = 0
    scores: List[float] = field(default_factory=list)
    category_filter: List[str] = field(default_factory=list)

    # ── Agent-execution eval metadata. `_populate_ctx_from_observations`, which
    # used to set these fields, was deleted with the legacy chat pipeline;
    # nothing sets or reads them today — dead fields. ───────────────────────────
    agent_steps: Optional[int] = None
    agent_tools_called: List[str] = field(default_factory=list)
    agent_retry_count: Optional[int] = None
    agent_final_chunk_count: Optional[int] = None
    graded_context: Optional[str] = None

    # ── Correlation/Request ID ──────────────────────────────────────────────
    request_id: Optional[str] = None

    # ── Dead config fields — populated by the deleted legacy pipeline's
    # `_build_context` from `system_configs` keys that have since been
    # removed (`agent_max_steps`, `agent_enough_chunks`, `use_deterministic_router`);
    # nothing sets or reads them today. ──────────────────────────────────────
    agent_max_steps: int = 6
    agent_enough_chunks: int = 8
    use_deterministic_router: bool = False

    def __deepcopy__(self, memo):
        # Return self directly to prevent copy.deepcopy from failing on non-pickleable
        # attributes (like AsyncSession, chains, embeddings, etc.) while sharing state.
        return self
