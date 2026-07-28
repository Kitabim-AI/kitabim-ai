# RAG Answer Quality: Reference-Free Evaluation Scoring

**Date:** 2026-07-27
**Status:** Draft (pending review)

## Problem

`rag_evaluations` has four Ragas-style columns (`faithfulness_score`, `answer_relevance_score`, `context_precision_score`, `context_recall_score`) added by migrations `042_add_ragas_columns.sql`/`044_...`, but nothing computes them — every row is written with `scores=[1.0]*len(observations)` (a placeholder) and `eval_status="completed"` regardless of actual quality. `stats_router.py` already returns `avg_faithfulness`/`avg_answer_relevance` fields in its response schema, hardcoded to `None`. The only live quality signal today is the thumbs up/down `user_feedback` column.

This blocks evaluating any future retrieval change (reranking, hybrid search, etc.) with real evidence — right now "did this help?" can only be answered by spot-checking transcripts. This spec wires up automatic, reference-free scoring so there's a quantitative baseline before that follow-on work starts.

## Existing state

- `ChatOrchestrator.stream_response` (`packages/backend-core/app/services/chat/orchestrator.py:316-343`) creates the `rag_evaluations` row after the answer streams, already populating `question`, `answer`, and `retrieved_context` (the graded chunk context), then hardcodes `eval_status="completed"` and commits. `answer` is `fixed_text` (`fix_malformed_citations(accumulated_text)`, line 316) — the identical string also passed to `conv_repo.save_turn(answer=fixed_text, ...)` (line 350) that persists the turn into `conversation_messages`. There's no separate/approximate copy: the judge scores the exact text the user saw, and `retrieved_context` is the exact `graded_context` the answer agent was given, not a re-derived approximation.
- `RAGEvaluationsRepository` extends `BaseRepository`, which already provides `get(id)` and `update_one(id, **kwargs)` — no new repository methods are needed to fetch-then-write-back scores.
- The worker registers job functions as a flat list in `services/worker/worker.py:53-64` (`WorkerSettings.functions = [...]`). `services/worker/jobs/knowledge_graph_job.py` is the template for a job: `log_json` on start, `async with async_session_factory() as session:`, config resolved via `SystemConfigsRepository(session).get_value("key", "default")`, then commit.
- Post-event job enqueueing (as opposed to a cron job) has one precedent: `books_router.py:1797-1810` opens an arq pool, calls `enqueue_job("knowledge_graph_job", book_id=book_id, _job_id=f"knowledge_graph:{book_id}")` for dedup, wrapped in try/except with `log_json` on failure. `orchestrator.py` itself has no existing enqueue calls today.
- Model selection for LLM calls is resolved via `SystemConfigsRepository.get_value(...)` (e.g. `gemini_chat_model`, `gemini_embedding_model`), not `settings.*` — that pattern is reused here for a new `gemini_judge_model` key.
- `stats_router.py:188-222` aggregates `user_feedback` thumbs counts via `case()` inside a `select(...)`; the `avg_faithfulness`/`avg_answer_relevance` fields sit alongside it, currently hardcoded `None`.
- No migration is needed for this spec — all four score columns, `eval_status`, `answer`, and `retrieved_context` already exist on `RAGEvaluation` (`packages/backend-core/app/db/models.py:531-610`).

## Design

### Metric scope

Three reference-free metrics, each a single LLM-judge call over data already captured on the row:

- **`faithfulness_score`** — is the answer grounded in `retrieved_context`, or does it assert things the context doesn't support?
- **`answer_relevance_score`** — does the answer actually address `question`?
- **`context_precision_score`** — are the chunks in `retrieved_context` relevant to `question` (irrespective of the answer)?

`context_recall_score` is explicitly **not** computed — it requires a ground-truth reference answer, which doesn't exist for live chat traffic. The column stays permanently null under this design. Building a labeled golden set for it is a possible future addition, out of scope here.

### Judge module

New file `packages/backend-core/app/services/rag/judge.py` with a single async function:

```python
async def score_answer(question: str, answer: str, context: str) -> JudgeScores
# JudgeScores: faithfulness, answer_relevance, context_precision (each 0.0-1.0)
```

This issues **one** Gemini call per turn (not three) with a single combined judge prompt that reasons about all three metrics together and returns structured JSON: `{"faithfulness": .., "answer_relevance": .., "context_precision": ..}`. Chosen over three separate calls to keep eval overhead to 1 extra LLM call/turn instead of 3, given every turn is scored with no sampling — the trade-off (a somewhat more complex combined prompt vs. three focused single-metric prompts) was accepted deliberately for cost. Custom-written prompt, not the `ragas` library (avoids its LangChain-flavored integration assumptions and fits existing prompt-authoring conventions here). The model is resolved via `SystemConfigsRepository.get_value("gemini_judge_model", "<default>")`, consistent with how `gemini_chat_model`/`gemini_embedding_model` are resolved elsewhere. Each of the three scores in the response is clamped to `0.0`–`1.0` after parsing. Exact prompt wording is an implementation detail to be authored via `/prompt-engineer` conventions when this spec is implemented — not finalized here.

Edge case: if `retrieved_context` is empty (the agent surfaced zero chunks), `score_answer` is still called with `context=""` rather than skipped — the prompt instructs the judge that an empty context means `context_precision` is trivially `0.0`, and `faithfulness` should score low for any answer that isn't a "no answer found" response. Handling this inside the single combined prompt (rather than special-casing it in code) keeps the one-call design intact.

### Worker job

New file `services/worker/jobs/rag_eval_job.py`:

```python
async def rag_eval_job(ctx, eval_id: int) -> None
```

Steps: `log_json` start → open `async_session_factory()` → fetch the row via `RAGEvaluationsRepository(session).get(eval_id)` → call `score_answer(question, answer, context)` (single LLM call) → `update_one(eval_id, faithfulness_score=.., answer_relevance_score=.., context_precision_score=.., eval_status="completed")` → commit.

On any exception from the judge call (timeout, malformed JSON, rate limit): catch it, `log_json` at error level, `update_one(eval_id, eval_status="failed")`, commit, and **do not re-raise**. This is a deliberate single-attempt policy — arq's default retry behavior isn't used here, since a quality-scoring job that keeps retrying against a consistently-failing judge call just adds noise. A `"failed"` row is a visible, queryable signal on its own.

Register `rag_eval_job` in `WorkerSettings.functions` (`services/worker/worker.py`).

### Orchestrator change

`orchestrator.py` (~line 319): change the hardcoded `eval_status="completed"` at row creation to `eval_status="pending"`. Immediately after the existing `db_session.commit()` (~line 343), enqueue the scoring job:

```python
redis_pool = await arq.create_pool(arq.connections.RedisSettings.from_dsn(settings.redis_url))
try:
    await redis_pool.enqueue_job(
        "rag_eval_job", eval_id=eval_record.id, _job_id=f"rag_eval:{eval_record.id}"
    )
finally:
    await redis_pool.aclose()
```

Wrapped in try/except with `log_json` on failure. An enqueue failure must never affect the chat response already streamed to the user — the row simply stays `"pending"` (see Error handling).

Every turn is scored (no sampling) — this is the simplest starting point; revisit if judge-call volume/cost becomes a real concern once there's usage data to justify it.

### Stats API change

`stats_router.py` (~lines 200-221): add `func.avg(RAGEvaluation.faithfulness_score)`, `func.avg(RAGEvaluation.answer_relevance_score)`, and `func.avg(RAGEvaluation.context_precision_score)` to the existing aggregation `select(...)`, replacing the two hardcoded `None` placeholders and adding a new `avg_context_precision` response field. Uses whatever overall/windowed grouping the existing query already applies to the other stats in that endpoint.

`apps/frontend/src/components/admin/StatsPanel.tsx` already fully renders `avg_faithfulness`/`avg_answer_relevance` (fields at lines 38-39, cards at lines 421-456, with `avgFaithfulnessNoData`/`avgAnswerRelevanceNoData` i18n fallbacks) — built ahead of the backend actually populating them, so once this spec ships, real percentages appear with no frontend change needed for those two. This spec adds a matching third card for `avg_context_precision` (same pattern: `%`-formatted value, progress bar, "no data yet" fallback) plus `avgContextPrecision`/`avgContextPrecisionNoData` keys in `en.json`/`ug.json`, for consistency with the existing two.

### Error handling

- **Judge call fails** → job marks the row `"failed"`, logged, no retry. Queryable and distinguishable from `"completed"`/`"pending"`.
- **Enqueue fails** (e.g. Redis unavailable) → caught in the orchestrator, logged, chat response unaffected. The row stays `"pending"` indefinitely with no automatic recovery — accepted limitation of choosing per-turn enqueue over a periodic sweep; a Redis outage broad enough to break enqueueing is already a bigger operational problem elsewhere.
- **Empty `retrieved_context`** → not an error; `context_precision_score=0.0` is the correct, meaningful value.

### Testing

- `judge.py` unit tests: mock the LLM call, verify all three scores parse/clamp to `[0.0, 1.0]`, verify behavior on malformed judge output.
- `rag_eval_job` test: mock `score_answer`; assert `update_one` is called with the expected fields on success, and `eval_status="failed"` (no re-raise) when the judge call raises.
- `stats_router_test.py`: extend with seeded `rag_evaluations` rows asserting `avg_faithfulness`/`avg_answer_relevance`/`avg_context_precision` reflect the seeded scores.
- No new frontend test suite for `StatsPanel.tsx` — manual verification that the third card renders correctly once real data flows through is sufficient for this small, consistent addition.

## Explicitly out of scope

- Computing `context_recall_score` — no ground truth exists for live traffic; would require a separately curated golden set.
- Sampling/throttling judge calls — every turn is scored for now.
- Retry/backoff/dead-letter handling for failed judge jobs beyond a single attempt + logged failure.
- Recovering `"pending"` rows if the enqueue call itself fails (no sweep/backfill job).
- Retrieval quality changes (reranking, hybrid search) — a separate follow-on spec, designed next, that will use this scoring pipeline as its before/after baseline.
- Finalized judge prompt wording — written during implementation, not in this design doc.
