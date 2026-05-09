"""QueryContext — per-request state passed to every RAG handler."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.db.models import Book


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
    book: Optional["Book"]          # None when is_global=True
    persona_prompt: Optional[str]
    character_categories: List[str]
    chat_history_str: str
    rag_chain: object
    rewrite_chain: object
    embeddings: object
    start_ts: float

    # ── Mutated by handlers ─────────────────────────────────────────────────
    query_vector: List[float] = field(default_factory=list)
    enriched_question: Optional[str] = None   # QueryRewriter rewrites follow-up question here
    use_current_volume_only: bool = False      # CurrentVolumeHandler sets this
    context_book_ids: List[str] = field(default_factory=list)  # from ChatRequest — reliable frontend-tracked context
    used_book_ids: List[str] = field(default_factory=list)     # populated by retrieval, returned in done event

    # ── Eval metadata — populated by handlers for facade _record_eval ───────
    retrieved_count: int = 0
    context_chars: int = 0
    scores: List[float] = field(default_factory=list)
    category_filter: List[str] = field(default_factory=list)

    # ── Agentic eval metadata — only set by AgentRAGHandler ─────────────────
    agent_steps: Optional[int] = None
    agent_tools_called: List[str] = field(default_factory=list)
    agent_retry_count: Optional[int] = None
    agent_final_chunk_count: Optional[int] = None
