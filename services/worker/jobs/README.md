# Worker Jobs

## Overview
Asynchronous ARQ task handlers executing Kitabim.AI's document processing and enrichment workloads: page OCR, text chunking, vector embedding, dictionary/rule spell-checking, auto-correction, book summarization, Neo4j knowledge graph extraction and entity resolution, and RAG answer evaluation.

## Interface
- `[auto_correct_job.py:auto_correct_job]`: `async def auto_correct_job(ctx, page_ids: List[int]) -> None`
- `[structure_job.py:structure_job]`: `async def structure_job(ctx, book_id: str) -> None`
- `[chunking_job.py:chunking_job]`: `async def chunking_job(ctx, book_id: Optional[str] = None, page_ids: Optional[List[int]] = None) -> None`
- `[embedding_job.py:embedding_job]`: `async def embedding_job(ctx, book_id: Optional[str] = None, page_ids: Optional[List[int]] = None) -> None`
- `[graph_resolution_job.py:graph_resolution_job]`: `async def graph_resolution_job(ctx, entity_ids: list[str]) -> None`
- `[knowledge_graph_job.py:VALID_SCOPES]`: `{'fiction', 'nonfiction'}`
- `[knowledge_graph_job.py:hijri_to_gregorian]`: `def hijri_to_gregorian(year_hijri: int) -> int`
- `[knowledge_graph_job.py:knowledge_graph_job]`: `async def knowledge_graph_job(ctx, book_id: str, scope: str) -> None`
- `[ocr_job.py:ocr_job]`: `async def ocr_job(ctx, book_id: str, page_ids: List[int]) -> None`
- `[rag_eval_job.py:rag_eval_job]`: `async def rag_eval_job(ctx: dict, eval_id: int) -> None`
- `[spell_check_job.py:spell_check_job]`: `async def spell_check_job(ctx, page_ids: List[int]) -> None`
- `[summary_job.py:summary_job]`: `async def summary_job(ctx, book_id: str) -> None`

## Invariants
- **Distributed Page Locking**: `ocr_job`, `chunking_job`, `embedding_job`, and `spell_check_job` acquire per-page Redis locks via `MultiPageLock` (`prefix='ocr'`, `'chunking'`, `'embedding'`, `'spell_check'`) and always release them in a `finally` block, exiting early if no page locks are acquired (`[ocr_job.py:ocr_job]`, `[chunking_job.py:chunking_job]`, `[embedding_job.py:embedding_job]`, `[spell_check_job.py:spell_check_job]`).
- **Concurrency & Session Isolation**:
  - `ocr_job` bounds direct page OCR by `asyncio.Semaphore(max_parallel_pages)` (from `ocr_max_parallel_pages`, default 4) and skips failing pages once `next_retry_count >= ocr_max_retry_count` (default 3) by marking `ocr_milestone='succeeded'` with `text=''` and `extra_fields={'skipped': True, ...}` (`[ocr_job.py:ocr_job]`).
  - `chunking_job` produces 0 chunks for TOC pages (`page.is_toc == True`), deletes obsolete chunks with `chunk_index >= len(chunks)`, and resets `Chunk.embedding = None` on upsert (`[chunking_job.py:chunking_job]`).
  - `embedding_job` requires system config `embed_gemini_model` (raises `RuntimeError` if missing) and only embeds chunks where `Chunk.embedding.is_(None)` ordered by `chunk_index` (`[embedding_job.py:embedding_job]`).
  - `auto_correct_job` and `spell_check_job` bound concurrency via `asyncio.Semaphore` (`settings.max_parallel_auto_correct`, `settings.max_parallel_spell_check`) (`[auto_correct_job.py:auto_correct_job]`, `[spell_check_job.py:spell_check_job]`).
- **Knowledge Graph & Entity Resolution**:
  - `knowledge_graph_job` requires `scope in VALID_SCOPES` (`{'fiction', 'nonfiction'}`) and `settings.gemini_api_key`; if `kg_enabled != 'true'` or the book has no chunks, it resets `Book.graph_milestone = 'idle'` and returns early (`[knowledge_graph_job.py:knowledge_graph_job]`).
  - `knowledge_graph_job` scopes entity `book_id` to `str(book_id)` only when `scope == 'fiction'` (`None` for `'nonfiction'`) and only enqueues entities to `GraphResolutionQueueRepository` when `save_errors == 0` (`[knowledge_graph_job.py:knowledge_graph_job]`).
  - `graph_resolution_job` processes each `entity_id` sequentially in an isolated PostgreSQL session, marking failed entities as `'failed'` in `GraphResolutionQueueRepository` without aborting remaining entities (`[graph_resolution_job.py:graph_resolution_job]`).
- **Summaries & RAG Evaluation**:
  - `summary_job` requires `rag_gemini_chat_model` and `embed_gemini_model`, excludes TOC and empty pages, and caps input text via `_sample_text` (40% head, 20% middle, 40% tail) (`[summary_job.py:summary_job]`, `[summary_job.py:_sample_text]`).
  - `rag_eval_job` is single-attempt best-effort: it catches exceptions, marks `eval_status = 'failed'`, and does not re-raise so ARQ does not retry (`[rag_eval_job.py:rag_eval_job]`).

## Side Effects
- **PostgreSQL & Pipeline Telemetry**: Mutates `Book`, `Page`, `Chunk`, `BookSummary`, `PipelineEvent`, `RAGEvaluation`, and `graph_resolution_queue` tables, and recalculates book milestones via `BookMilestoneService` (`[ocr_job.py:ocr_job]`, `[chunking_job.py:chunking_job]`, `[embedding_job.py:embedding_job]`, `[spell_check_job.py:spell_check_job]`, `[auto_correct_job.py:auto_correct_job]`, `[summary_job.py:summary_job]`, `[rag_eval_job.py:rag_eval_job]`).
- **Neo4j Knowledge Graph**: Deletes book subgraphs, initializes schema constraints, bulk upserts entities/relationships/embeddings, and resolves duplicate entities in Neo4j (`[knowledge_graph_job.py:knowledge_graph_job]`, `[graph_resolution_job.py:graph_resolution_job]`).
- **Redis Locks**: Acquires and releases distributed page locks via `MultiPageLock` (`[ocr_job.py:ocr_job]`, `[chunking_job.py:chunking_job]`, `[embedding_job.py:embedding_job]`, `[spell_check_job.py:spell_check_job]`).
- **External AI APIs & Storage**: Downloads PDF files from storage to `settings.uploads_dir / f'{book_id}.pdf'` (`[ocr_job.py:ocr_job]`), and invokes Google Gemini live and Batch APIs for vision OCR, text embeddings, book summarization, knowledge graph extraction, and RAG judge scoring (`[ocr_job.py:ocr_job]`, `[embedding_job.py:embedding_job]`, `[summary_job.py:summary_job]`, `[knowledge_graph_job.py:knowledge_graph_job]`, `[rag_eval_job.py:rag_eval_job]`).

## Verification
- Run: `pytest services/worker/tests`
