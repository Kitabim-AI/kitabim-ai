"""Agent configuration constants — single source of truth for numeric limits."""

# ── ReAct loop ────────────────────────────────────────────────────────────────
AGENT_MAX_STEPS = 6  # maximum ReAct iterations per round
AGENT_ENOUGH_CHUNKS = 8  # early-exit: stop once this many chunks are collected
AGENT_MAX_CONTEXT_CHUNKS = 25  # hard cap on chunks passed to the answer LLM

# ── Context grading (grade_context node) ─────────────────────────────────────
GRADE_RELATIVE_THRESHOLD = 0.85  # keep chunks scoring >= top_score × this value
MIN_CHUNKS_AFTER_GRADING = 3  # never filter below this many chunks

# ── LLM reranker (reranker.py) ────────────────────────────────────────────────
# Caps the deduped candidate set sent to the reranker LLM call, protecting
# prompt size/cost against a turn where the agent calls search_chunks many times.
RERANK_MAX_INPUT_CHUNKS = 50

# ── Hybrid search fusion (retrieval.py) ───────────────────────────────────────
# Standard Reciprocal Rank Fusion constant: score(chunk) = sum(1 / (k + rank)).
RRF_K = 60

# ── Context-switch detection ──────────────────────────────────────────────────
# When the LLM reuses context_book_ids from the previous answer and the top
# similarity score is below this threshold, the search is transparently broadened
# to all books. Prevents stale context from poisoning topic-switch queries.
# Calibrated from observed scores: good match ≈ 0.75+, topic mismatch ≈ 0.62.
CONTEXT_SWITCH_SCORE_THRESHOLD = 0.72
