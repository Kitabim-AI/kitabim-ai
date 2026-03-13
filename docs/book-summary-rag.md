# Design: Hierarchical RAG with Book Summaries

**Status:** Implemented
**Date:** 2026-03-10

---

## Problem

Global chat currently runs similarity search across all chunks from all books simultaneously. This produces noisy retrieval — chunks from irrelevant books score high due to shared vocabulary — and limits answer quality.

Current global search flow in `rag_service.py`:
1. Categorize question → `_categorize_question()` returns category labels
2. Look up book IDs by category (or fallback to recent books)
3. Similarity search across all chunks from all matching books

The category filter is coarse (label-based). There is no semantic understanding of which specific books are relevant to the question.

---

## Proposed Solution: Two-Stage Hierarchical Retrieval

Add a `book_summaries` table. At query time, use the summary embeddings to semantically identify the most relevant books, then restrict chunk search to those books.

```
User question
     │
     ▼
[Stage 1]  Embed question → pgvector search on book_summaries
           → returns top-K book IDs (e.g. 5 books)
     │
     ▼
[Stage 2]  Similarity search on chunks WHERE book_id IN (top-K books)
           → existing similarity_search() with book_ids filter
     │
     ▼
[Stage 3]  LLM answers using retrieved chunks (unchanged)
```

Stage 1 is fast: the summaries table will have at most a few hundred rows.
Stage 2 becomes faster: search space shrinks from all books to ~5 books.
Stage 3 is unchanged: same prompt template and LLM call.

---

## Database Changes

### New table: `book_summaries`

```sql
CREATE TABLE book_summaries (
    book_id       VARCHAR(64) PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,
    summary       TEXT         NOT NULL,
    embedding     vector(768)  NOT NULL,
    generated_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE INDEX idx_book_summaries_embedding
    ON book_summaries
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 50);
```

**Field notes:**
- `summary` — 200–500 word LLM-generated description of the book's content, themes, and topics. Written in the same language the book is in (Uyghur).
- `embedding` — 768-dim Gemini embedding of the summary, same model as chunk embeddings (`models/gemini-embedding-001`).
- `generated_at` — allows detecting stale summaries if book content changes.

No changes to existing tables.

---

## New Components

### 1. Summary Generation Job (`services/worker/jobs/summary_job.py`)

A new background job that generates a summary for a book after it reaches `ready` status.

**Inputs:** `book_id`
**Process:**
1. Load all page texts for the book from `pages` table (ordered by page_number)
2. If total text > ~15k chars, sample: first 30%, middle 20%, last 20% (avoids token limit issues on large books)
3. Call Gemini chat model with `SUMMARY_PROMPT` (see below)
4. Embed the resulting summary with `GeminiEmbeddings.aembed_documents()`
5. Upsert into `book_summaries`

**Summary prompt (`SUMMARY_PROMPT`):**
```
You are summarizing an Uyghur book for a semantic search index.
Write a 300-word summary in Uyghur covering:
- Main subject and scope
- Key themes, topics, and arguments
- Time period or geographic focus (if applicable)
- Notable people, places, or events discussed

Book title: {title}
Author: {author}

Book text (excerpts):
{text}

Summary:
```

**Error handling:** Job failure does not affect book availability. Books without summaries fall back to the existing category-based selection.

### 2. Pipeline Driver Hook (`services/worker/scanners/pipeline_driver.py`)

**No separate scanner needed.** The pipeline driver already detects the exact moment a book transitions to `ready` (step 4, `fully_ready_ids`). Enqueue the summary job there directly.

```python
# In run_pipeline_driver(), after marking books ready:
if newly_ready_book_ids:          # books that just transitioned (rowcount > 0)
    for book_id in newly_ready_book_ids:
        await ctx["redis"].enqueue_job("summary_job", book_id=book_id)
```

`newly_ready_book_ids` is the subset of `fully_ready_ids` where the UPDATE actually changed a row — i.e., books that were not already `ready`. This avoids duplicate jobs on re-runs.

This is the primary trigger. No polling delay; summary generation starts the moment embedding finishes.

**Backfill (deploy only):** Existing books that are already `ready` when this feature ships have no summary yet. A one-time query handles them — the summary scanner below covers this case.

### 2b. Summary Scanner — backfill and retry (`services/worker/scanners/summary_scanner.py`)

A lightweight scanner that runs every 5 minutes, catching two cases:
1. Books that existed before this feature was deployed (no summary yet)
2. Books whose summary job failed and need a retry

```python
# Pseudocode — runs every 5 minutes
books = await session.execute(
    select(Book.id)
    .outerjoin(BookSummary, Book.id == BookSummary.book_id)
    .where(Book.status == "ready")
    .where(BookSummary.book_id.is_(None))
    .limit(5)
    .with_for_update(skip_locked=True)
)
for book_id in book_ids:
    await redis.enqueue_job("summary_job", book_id=book_id)
```

This scanner is idempotent — once a summary row exists, the book is never re-enqueued.

### 3. Book Summaries Repository (`packages/backend-core/app/db/repositories/book_summaries.py`)

New repository following existing patterns in `chunks.py`.

```python
class BookSummariesRepository:

    async def summary_search(
        self,
        query_embedding: List[float],
        limit: int = 5,
        threshold: float = 0.30,
    ) -> List[str]:
        """Returns book_ids ordered by summary similarity to query."""
        ...

    async def upsert(self, book_id: str, summary: str, embedding: List[float]) -> None:
        ...

    async def get_by_book_id(self, book_id: str) -> Optional[BookSummary]:
        ...
```

### 4. SQLAlchemy Model (`packages/backend-core/app/db/models.py`)

Add `BookSummary` model alongside existing models:

```python
class BookSummary(Base):
    __tablename__ = "book_summaries"

    book_id      = Column(String(64), ForeignKey("books.id", ondelete="CASCADE"), primary_key=True)
    summary      = Column(Text, nullable=False)
    embedding    = Column(Vector(768), nullable=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())

    book = relationship("Book", back_populates="summary")
```

---

## Changes to Existing Code

### `rag_service.py` — `answer_question()` and `answer_question_stream()`

**Current global search logic:**
```python
# Existing: category-based book selection
categories = await _categorize_question(question)
book_ids = await books_repo.get_ids_by_categories(categories)
chunks = await chunks_repo.similarity_search(query_vector, book_ids)
```

**New global search logic:**
```python
# New: summary-based book selection with category fallback
query_vector = await embeddings.aembed_query(question)

book_ids = await book_summaries_repo.summary_search(
    query_embedding=query_vector,
    limit=SUMMARY_TOP_K,           # default: 5
    threshold=SUMMARY_THRESHOLD,   # default: 0.30
)

if not book_ids:
    # Fallback: existing category-based selection
    categories = await _categorize_question(question)
    book_ids = await books_repo.get_ids_by_categories(categories)

chunks = await chunks_repo.similarity_search(query_vector, book_ids)
```

Note: `query_vector` is computed once and reused in both stages — no extra embedding API call.

**Book-specific chat** (`book_id != "global"`) is unchanged.

### Configuration (`packages/backend-core/app/core/config.py`)

Add two new env vars:

```
SUMMARY_TOP_K=5           # Books to select in stage 1
SUMMARY_THRESHOLD=0.30    # Min similarity to include a book
```

---

## Migration

New Alembic migration:
- Creates `book_summaries` table
- Creates IVFFlat index on embedding column

After deploy, the summary scanner will automatically enqueue summary jobs for all existing `ready` books. No manual backfill script needed.

---

## Latency Impact

| Step | Before | After | Change |
|------|--------|-------|--------|
| Embed question | ~200ms | ~200ms | Same (vector reused) |
| Category LLM call | ~400ms | 0ms (eliminated for most queries) | -400ms |
| Summary search | — | ~20ms | +20ms |
| Chunk search | ~300ms (all books) | ~80ms (5 books) | -220ms |
| LLM answer | ~2000ms | ~2000ms | Same |
| **Total** | **~2900ms** | **~2300ms** | **-600ms** |

Summary-based retrieval eliminates the categorization LLM call, which is the second-largest latency contributor.

---

## Accuracy Impact

Expected improvements:
- Thematic queries (e.g. "مەن تارىخ ھەققىدە ئۇچۇر ئىزدەۋاتىمەن") retrieve from historically relevant books rather than keyword-matched categories
- Queries mentioning specific topics not captured by category labels are handled correctly
- Reduced noise from irrelevant books improves chunk ranking quality

Risk: If a book's summary is poor quality or missing, it may be excluded from search. Mitigated by fallback to category-based selection.

---

## Rollout Plan

1. Add `BookSummary` model and Alembic migration
2. Implement `BookSummariesRepository`
3. Implement `summary_job.py` and `summary_scanner.py`
4. Add `SUMMARY_TOP_K` and `SUMMARY_THRESHOLD` to config
5. Update `rag_service.py` with two-stage logic and fallback
6. Deploy — scanner will auto-generate summaries for existing books
7. Monitor `rag_evaluations` table for score changes (retrieved_count, scores columns)

Steps 1–4 can be done without affecting production behavior. Step 5 is the live change.

---

## Out of Scope

- Chapter-level or section-level embeddings (can be added later as a third tier)
- Summary regeneration when book content is edited (not currently supported anyway)
- Exposing summaries via API or UI
