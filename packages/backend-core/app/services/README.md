# Backend Services (`app/services`)

## Overview
Houses core business logic and domain processing pipelines for Kitabim AI, including document ingestion (PDF/DOCX), OCR text extraction, chunking, embeddings, spell checking, auto-correction, entity resolution, storage providers, rate limiting, and user management.

## Interface
- `[ocr_service.py:ocr_page_with_gemini]` — Performs single-page OCR text recognition via Gemini multimodal models.
- `[batch_ocr_service.py:submit_batch_ocr_job]` / `[batch_ocr_service.py:poll_and_process_batch_ocr_jobs]` — Manages batch OCR jobs.
- `[pdf_service.py:read_pdf_page_count]` / `[pdf_service.py:extract_pdf_cover]` / `[pdf_service.py:create_page_stubs]` — Extracts PDF page counts, rendered covers, and initializes page records.
- `[docx_service.py:extract_docx_pages]` / `[docx_service.py:extract_docx_cover]` — Ingests DOCX files, extracting text, headings, footnotes, and covers.
- `[chunking_service.py:ChunkingService]` — Splits page text into overlapping semantic chunks with Markdown structure awareness.
- `[batch_embedding_service.py:submit_batch_embedding_job]` / `[batch_embedding_service.py:poll_and_process_batch_embedding_jobs]` — Batch embedding pipeline.
- `[spell_check_service.py:run_spell_check_for_page]` — Uyghur spell checker identifying unknown words and calculating correction confidences.
- `[llm_spell_check_service.py:correct_page_text]` — Contextual LLM-based spell correction over full page text.
- `[auto_correct_service.py:apply_auto_corrections_to_page]` — Applies deterministic auto-correction rules to page text.
- `[entity_resolution_service.py:resolve_entity]` / `[entity_resolution_service.py:execute_merge]` — Entity deduplication, vector similarity matching, and alias management.
- `[history_extraction_service.py:HistoryExtractionService]` — Extracts historical entities, definitions, and facts from book text.
- `[dictionary_staging_service.py:DictionaryStagingService]` — Manages review, staging, and approval workflow for extracted historical terms.
- `[storage_service.py:StorageProvider]` / `[storage_service.py:storage]` — Unified file storage provider abstraction (`FileSystemStorageProvider`, `GCSStorageProvider`).
- `[cache_service.py:CacheService]` / `[cache_service.py:cache_service]` — Redis caching service providing get, set, delete, and pattern invalidation.
- `[chat_limit_service.py:ChatLimitService]` — Enforces daily query limits per user or IP address using Redis Lua atomic counters.
- `[token_service.py:store_refresh_token]` / `[token_service.py:validate_refresh_token]` — Refresh token hashing, validation, and revocation.
- `[user_service.py:get_user_by_id]` / `[user_service.py:create_user]` / `[user_service.py:update_user_role]` — User account management and role administration.
- `[book_milestone_service.py:BookMilestoneService]` — Manages lifecycle milestone transitions for books across pipeline stages.
- [Chat Orchestration Subsystem](./chat/README.md) — Conversational agent, context grading, and query routing.
- [RAG Subsystem](./rag/README.md) — Retrieval-augmented generation, embeddings, reranking, and evaluation.

## Invariants
- `[token_service.py:hash_token]` — Refresh tokens are stored strictly as SHA-256 hashes and never in plaintext.
- `[chunking_service.py:ChunkingService]` — Respects heading hierarchy and avoids splitting mid-sentence across chunk boundaries.
- `[spell_check_service.py:run_spell_check_for_page]` — Skips standalone numerals, punctuation, and known entity names during spell checking.
- `[storage_service.py:get_storage_provider]` — Instantiates `GCSStorageProvider` when `GCS_BUCKET_NAME` is configured, otherwise falls back to `FileSystemStorageProvider`.

## Side Effects
- Reads and writes uploaded files and rendered page images to local disk (`./data/`) or Google Cloud Storage.
- Executes batch jobs and model inferences against Google Gemini API.
- Mutates records in PostgreSQL database tables across multiple domains.
- Modifies Redis cache entries, rate limit counters, and distributed lock keys.

## Verification
- Run: `pytest packages/backend-core/tests`
