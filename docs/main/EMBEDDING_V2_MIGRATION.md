# Gemini Embedding 2 Migration Plan

Upgrade from `models/gemini-embedding-001` (768 dimensions) to Gemini Embedding 2 (3072 dimensions).

**Scale:** 497,149 chunks across 554 books + 554 book_summaries  
**Strategy:** Dual column — new embeddings built in background, single atomic cutover once 100% complete  
**Rollback:** Clean cutover only (no rollback path needed)

---

## Phase 0 — Verify model ID (before writing any code)

Confirm the exact model string for `langchain_google_genai`. "gemini-embedding-2" is the marketing name; the API string is likely `models/gemini-embedding-exp-03-07` or `models/gemini-embedding-2-preview-04-23`. Run a quick local test:

```python
from langchain_google_genai import GoogleGenerativeAIEmbeddings
e = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-exp-03-07", task_type="RETRIEVAL_DOCUMENT")
result = await e.aembed_documents(["test"])
print(len(result[0]))  # must be 3072
```

Also check the Gemini API quota/RPM for the new model — rate limits differ from embedding-001.

---

## Phase 1 — Schema: add v2 columns

**Migration `035_add_embedding_v2_columns.sql`:**

```sql
ALTER TABLE chunks ADD COLUMN embedding_v2 vector(3072);
ALTER TABLE book_summaries ADD COLUMN embedding_v2 vector(3072);
```

No indexes yet — building them now would slow every batch insert. Deploy and run. Zero search impact; old `embedding` column is untouched.

---

## Phase 2 — Re-embedding infrastructure

**New files:**
- `services/worker/scanners/reembedding_scanner.py` — mirrors the existing scanner pattern; finds books where any chunk has `embedding_v2 IS NULL`, dispatches one `reembedding_job` per book
- `services/worker/jobs/reembedding_job.py` — processes a single book:
  1. Instantiates `GeminiEmbeddings(model_name=<v2-model-id>)` directly (does NOT read from `system_configs` — that key still points to the old model)
  2. Queries `chunks WHERE book_id = ? AND embedding_v2 IS NULL`, batches of 50
  3. Writes results to `embedding_v2` only
  4. After all chunks for a book are done, re-embeds that book's row in `book_summaries.embedding_v2`

The existing `embedding_job.py` and `summary_job.py` keep running unchanged for newly ingested books — they write to `embedding` (v1). New books get v1 embeddings during migration; the re-embedding scanner picks them up automatically.

**Progress query:**
```sql
SELECT
  COUNT(*) FILTER (WHERE embedding_v2 IS NULL)      AS remaining,
  COUNT(*) FILTER (WHERE embedding_v2 IS NOT NULL)  AS done,
  COUNT(*)                                           AS total
FROM chunks;
```

---

## Phase 3 — Run re-embedding

**Time estimate:** 497,149 chunks ÷ 50 per batch = 9,943 API calls. Expect **2–4 hours** depending on worker concurrency and API throughput. Book summaries (554 rows) add negligible time.

The existing `_EMBED_BREAKER` circuit-breaker in `packages/backend-core/app/langchain/models.py` handles transient rate-limit errors automatically.

Do not proceed to Phase 4 until both queries return 0:
```sql
SELECT COUNT(*) FROM chunks WHERE embedding_v2 IS NULL;
SELECT COUNT(*) FROM book_summaries WHERE embedding_v2 IS NULL;
```

---

## Phase 4 — Build indexes on v2 columns (pre-cutover)

**Migration `036_create_embedding_v2_indexes.sql`:**

```sql
CREATE INDEX CONCURRENTLY idx_chunks_embedding_v2
  ON chunks USING hnsw (embedding_v2 vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX CONCURRENTLY idx_book_summaries_embedding_v2
  ON book_summaries USING ivfflat (embedding_v2 vector_cosine_ops)
  WITH (lists = 50);
```

`CONCURRENTLY` means no table locks — live traffic continues normally. Expect 10–30 minutes on 497k rows.

---

## Phase 5 — Atomic cutover (migration + deploy, done together)

**Migration `037_cutover_to_embedding_v2.sql`:**

```sql
BEGIN;

ALTER TABLE chunks         RENAME COLUMN embedding    TO embedding_v1;
ALTER TABLE chunks         RENAME COLUMN embedding_v2 TO embedding;
ALTER TABLE book_summaries RENAME COLUMN embedding    TO embedding_v1;
ALTER TABLE book_summaries RENAME COLUMN embedding_v2 TO embedding;

ALTER INDEX idx_chunks_embedding              RENAME TO idx_chunks_embedding_v1;
ALTER INDEX idx_chunks_embedding_v2           RENAME TO idx_chunks_embedding;
ALTER INDEX idx_book_summaries_embedding      RENAME TO idx_book_summaries_embedding_v1;
ALTER INDEX idx_book_summaries_embedding_v2   RENAME TO idx_book_summaries_embedding;

UPDATE system_configs
  SET value = '<exact-v2-model-id>'
  WHERE key = 'gemini_embedding_model';

COMMIT;
```

**Code changes in the same deploy:**

| File | Change |
|------|--------|
| `packages/backend-core/app/db/models.py:213` | `Vector(768)` → `Vector(3072)` on `Chunk.embedding` |
| `packages/backend-core/app/db/models.py:533` | `Vector(768)` → `Vector(3072)` on `BookSummary.embedding` |
| `packages/backend-core/app/db/seeds.py` | Update default seed value for `gemini_embedding_model` |

No changes needed in repositories or RAG handlers — the raw SQL `CAST(:embedding AS vector)` is dimension-agnostic, and the model name is read from `system_configs` at runtime.

**Brief cutover window risk:** Between when migration 037 commits and when new containers are live (~2–5 seconds), searches hitting old containers will get a pgvector dimension-mismatch error. The existing RAG error handling surfaces this as a failed search, not a crash. This is the minimum possible disruption for a clean cutover.

After deploy: stop the `reembedding_scanner`.

---

## Phase 6 — Validate (1–2 days)

- Run real queries and verify RAG result quality
- Watch logs for any `vector dimension` errors (should be zero post-deploy)
- The `embedding_v1` columns remain in the DB as an unused safety net during this window

---

## Phase 7 — Cleanup (~1 week after cutover)

**Migration `038_drop_embedding_v1_columns.sql`:**

```sql
DROP INDEX IF EXISTS idx_chunks_embedding_v1;
DROP INDEX IF EXISTS idx_book_summaries_embedding_v1;

ALTER TABLE chunks         DROP COLUMN embedding_v1;
ALTER TABLE book_summaries DROP COLUMN embedding_v1;
```

This reclaims significant disk space (768-dim vectors × 497k rows).

---

## Summary of all changes

| Artifact | Action | Phase |
|---|---|---|
| `035_add_embedding_v2_columns.sql` | New migration | 1 |
| `036_create_embedding_v2_indexes.sql` | New migration | 4 |
| `037_cutover_to_embedding_v2.sql` | New migration | 5 |
| `038_drop_embedding_v1_columns.sql` | New migration | 7 |
| `services/worker/scanners/reembedding_scanner.py` | New file | 2 |
| `services/worker/jobs/reembedding_job.py` | New file | 2 |
| `packages/backend-core/app/db/models.py` | `Vector(768)→3072` × 2 | 5 deploy |
| `packages/backend-core/app/db/seeds.py` | Update model name seed | 5 deploy |
