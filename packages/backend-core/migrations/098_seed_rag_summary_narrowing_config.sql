-- Migration: 098_seed_rag_summary_narrowing_config.sql
-- Description: Seed rag_summary_narrowing_enabled system configuration key.
--   'false' = retrieval agent searches chunks across the whole library directly
--   (no search_books_by_summary pre-narrowing). Missing row = 'true' in code
--   (legacy behavior), so rollback restores the old pipeline.
-- Author: Kitabim.AI
-- Date: 2026-10-13

BEGIN;

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'rag_summary_narrowing_enabled',
    'false',
    'When true, the chat retrieval agent first narrows content questions to ~30 books by book-summary similarity (search_books_by_summary) before chunk search. When false, it searches chunks across the whole library directly. get_book_summary for "what is this book about" questions is unaffected.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

COMMIT;
