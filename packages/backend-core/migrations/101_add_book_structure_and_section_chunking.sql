-- Migration 101: Add book structure milestone, book_sections table, and section-stream chunking columns
BEGIN;

-- 1. Books columns for structure milestone, book-scoped claim/retry state, and OCR backfill provenance
ALTER TABLE books
    ADD COLUMN IF NOT EXISTS structure_milestone VARCHAR(20) NOT NULL DEFAULT 'idle',
    ADD COLUMN IF NOT EXISTS structure_retry_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS structure_claimed_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS chunking_retry_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS chunking_claimed_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS embedding_retry_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS embedding_claimed_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS ocr_version VARCHAR(32) NULL,
    ADD COLUMN IF NOT EXISTS ocr_backfill_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS gcs_ocr_backup_uri TEXT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'books_structure_milestone_check'
    ) THEN
        ALTER TABLE books
            ADD CONSTRAINT books_structure_milestone_check
            CHECK (structure_milestone IN ('idle', 'in_progress', 'complete', 'partial_failure', 'failed'));
    END IF;
END $$;

-- Standardize any legacy 'succeeded' book-level milestone rows to 'complete'
-- and reset any legacy 'partial_failure' chunking/embedding rows to 'idle'
UPDATE books SET ocr_milestone = 'complete' WHERE ocr_milestone = 'succeeded';
UPDATE books SET spell_check_milestone = 'complete' WHERE spell_check_milestone = 'succeeded';
UPDATE books SET chunking_milestone = 'complete' WHERE chunking_milestone = 'succeeded';
UPDATE books SET embedding_milestone = 'complete' WHERE embedding_milestone = 'succeeded';
UPDATE books SET graph_milestone = 'complete' WHERE graph_milestone = 'succeeded';
UPDATE books SET chunking_milestone = 'idle' WHERE chunking_milestone = 'partial_failure';
UPDATE books SET embedding_milestone = 'idle' WHERE embedding_milestone = 'partial_failure';

-- Stamp ocr_version = 'surya-2.5-v2' on Surya local PDFs uploaded on or after 2026-11-08T00:00:00Z
UPDATE books
SET ocr_version = 'surya-2.5-v2'
WHERE file_type = 'pdf'
  AND source = 'surya_local'
  AND upload_date >= '2026-11-08T00:00:00Z'::timestamptz
  AND ocr_version IS NULL;

-- Set structure_milestone = 'complete' on books that have already finished OCR
-- so deploy does not trigger a bulk re-chunk; books still in OCR remain 'idle'.
-- Existing books without book_sections are triggered in controlled batches via
-- scripts/trigger_remaining_structure_backfill.py or replace-ocr.
UPDATE books
SET structure_milestone = CASE
    WHEN ocr_milestone = 'complete' THEN 'complete'
    ELSE 'idle'
END;

-- 2. Pages columns for sidecar detected page number and manual override flag
ALTER TABLE pages
    ADD COLUMN IF NOT EXISTS detected_page_number INTEGER NULL,
    ADD COLUMN IF NOT EXISTS content_page_number_manual BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_pages_book_content_page
    ON pages (book_id, content_page_number);

-- 3. Book sections table (two-tier chapter -> work tree per book)
CREATE TABLE IF NOT EXISTS book_sections (
    id BIGSERIAL PRIMARY KEY,
    book_id VARCHAR(64) NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    parent_id BIGINT NULL REFERENCES book_sections(id) ON DELETE CASCADE,
    section_index INTEGER NOT NULL,
    level SMALLINT NOT NULL DEFAULT 1,
    section_type VARCHAR(32) NOT NULL DEFAULT 'chapter',
    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    toc_printed_page INTEGER NULL,
    start_page INTEGER NOT NULL,
    start_block_index INTEGER NOT NULL DEFAULT 0,
    end_page INTEGER NOT NULL,
    end_block_index INTEGER NOT NULL DEFAULT 999999,
    source VARCHAR(32) NOT NULL DEFAULT 'header_detected',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT book_sections_book_id_section_index_key UNIQUE (book_id, section_index),
    CONSTRAINT book_sections_level_check CHECK (level IN (1, 2)),
    CONSTRAINT book_sections_type_check CHECK (
        section_type IN ('chapter', 'work', 'front_matter', 'back_matter', 'synthetic_body')
    ),
    CONSTRAINT book_sections_source_check CHECK (
        source IN ('toc_matched', 'toc_interpolated', 'header_detected', 'synthetic_body')
    )
);

CREATE INDEX IF NOT EXISTS idx_book_sections_book_id
    ON book_sections (book_id);
CREATE INDEX IF NOT EXISTS idx_book_sections_parent_id
    ON book_sections (parent_id);
CREATE INDEX IF NOT EXISTS idx_book_sections_book_norm_title
    ON book_sections (book_id, normalized_title);
CREATE INDEX IF NOT EXISTS idx_book_sections_norm_title
    ON book_sections (normalized_title);

-- 4. Chunks columns for cross-page spans, section reference, and text hash carry-over
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS end_page_number INTEGER NULL,
    ADD COLUMN IF NOT EXISTS section_id BIGINT NULL REFERENCES book_sections(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS text_hash VARCHAR(64) NULL;

CREATE INDEX IF NOT EXISTS idx_chunks_book_section
    ON chunks (book_id, section_id);
CREATE INDEX IF NOT EXISTS idx_chunks_book_text_hash
    ON chunks (book_id, text_hash);

-- 5. System configs for online batch embedding timeout and book-scoped batch embedding chunk cap
INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'embed_gemini_timeout',
    '15',
    'Timeout in seconds for Gemini online query embedding API calls',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'embed_gemini_batch_timeout',
    '45',
    'Timeout in seconds for Gemini batchEmbedContents document sub-batch API calls',
    NOW()
)
ON CONFLICT (key) DO UPDATE
SET value = '45', updated_at = NOW();

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'embed_batch_max_chunks_per_job',
    '5000',
    'Maximum number of chunks packed into a single Gemini Batch Embedding job per book',
    NOW()
)
ON CONFLICT (key) DO UPDATE
SET value = '5000', updated_at = NOW();

COMMIT;
