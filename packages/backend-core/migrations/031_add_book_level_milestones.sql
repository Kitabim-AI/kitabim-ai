-- Add book-level milestone columns for efficient status display
-- These are denormalized from page-level milestones for performance

ALTER TABLE books
ADD COLUMN ocr_milestone VARCHAR(20) DEFAULT 'idle' NOT NULL,
ADD COLUMN chunking_milestone VARCHAR(20) DEFAULT 'idle' NOT NULL,
ADD COLUMN embedding_milestone VARCHAR(20) DEFAULT 'idle' NOT NULL,
ADD COLUMN word_index_milestone VARCHAR(20) DEFAULT 'idle' NOT NULL,
ADD COLUMN spell_check_milestone VARCHAR(20) DEFAULT 'idle' NOT NULL;

-- Add check constraints for valid milestone values
ALTER TABLE books ADD CONSTRAINT books_ocr_milestone_check
  CHECK (ocr_milestone IN ('idle', 'in_progress', 'complete', 'partial_failure', 'failed'));

ALTER TABLE books ADD CONSTRAINT books_chunking_milestone_check
  CHECK (chunking_milestone IN ('idle', 'in_progress', 'complete', 'partial_failure', 'failed'));

ALTER TABLE books ADD CONSTRAINT books_embedding_milestone_check
  CHECK (embedding_milestone IN ('idle', 'in_progress', 'complete', 'partial_failure', 'failed'));

ALTER TABLE books ADD CONSTRAINT books_word_index_milestone_check
  CHECK (word_index_milestone IN ('idle', 'in_progress', 'complete', 'partial_failure', 'failed'));

ALTER TABLE books ADD CONSTRAINT books_spell_check_milestone_check
  CHECK (spell_check_milestone IN ('idle', 'in_progress', 'complete', 'partial_failure', 'failed'));

-- Add indexes for filtering by milestone status
CREATE INDEX idx_books_ocr_milestone ON books(ocr_milestone) WHERE ocr_milestone != 'complete';
CREATE INDEX idx_books_chunking_milestone ON books(chunking_milestone) WHERE chunking_milestone != 'complete';
CREATE INDEX idx_books_embedding_milestone ON books(embedding_milestone) WHERE embedding_milestone != 'complete';
CREATE INDEX idx_books_word_index_milestone ON books(word_index_milestone) WHERE word_index_milestone != 'complete';
CREATE INDEX idx_books_spell_check_milestone ON books(spell_check_milestone) WHERE spell_check_milestone != 'complete';

-- Backfill existing books with computed milestone values
-- This is a one-time operation to set initial values based on page milestones

-- Helper function to compute milestone status from page counts
CREATE OR REPLACE FUNCTION compute_milestone_status(
  done_count BIGINT,
  failed_count BIGINT,
  active_count BIGINT,
  total_count BIGINT
) RETURNS VARCHAR(20) AS $$
BEGIN
  IF total_count = 0 THEN
    RETURN 'idle';
  END IF;

  -- All pages succeeded
  IF done_count = total_count THEN
    RETURN 'complete';
  END IF;

  -- All pages finished (some failed, some succeeded)
  IF done_count + failed_count = total_count THEN
    IF failed_count > 0 THEN
      RETURN 'partial_failure';
    ELSE
      RETURN 'complete';
    END IF;
  END IF;

  -- All pages failed
  IF failed_count = total_count THEN
    RETURN 'failed';
  END IF;

  -- Mixed state (some done, some pending/active)
  IF done_count > 0 OR active_count > 0 OR failed_count > 0 THEN
    RETURN 'in_progress';
  END IF;

  -- Default: idle
  RETURN 'idle';
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Backfill OCR milestone
UPDATE books b
SET ocr_milestone = (
  SELECT compute_milestone_status(
    COUNT(*) FILTER (WHERE p.ocr_milestone = 'succeeded'),
    COUNT(*) FILTER (WHERE p.ocr_milestone IN ('failed', 'error')),
    COUNT(*) FILTER (WHERE p.ocr_milestone = 'in_progress'),
    COUNT(*)
  )
  FROM pages p
  WHERE p.book_id = b.id
);

-- Backfill Chunking milestone
UPDATE books b
SET chunking_milestone = (
  SELECT compute_milestone_status(
    COUNT(*) FILTER (WHERE p.chunking_milestone = 'succeeded'),
    COUNT(*) FILTER (WHERE p.chunking_milestone IN ('failed', 'error')),
    COUNT(*) FILTER (WHERE p.chunking_milestone = 'in_progress'),
    COUNT(*)
  )
  FROM pages p
  WHERE p.book_id = b.id
);

-- Backfill Embedding milestone
UPDATE books b
SET embedding_milestone = (
  SELECT compute_milestone_status(
    COUNT(*) FILTER (WHERE p.embedding_milestone = 'succeeded'),
    COUNT(*) FILTER (WHERE p.embedding_milestone IN ('failed', 'error')),
    COUNT(*) FILTER (WHERE p.embedding_milestone = 'in_progress'),
    COUNT(*)
  )
  FROM pages p
  WHERE p.book_id = b.id
);

-- Backfill Word Index milestone
UPDATE books b
SET word_index_milestone = (
  SELECT compute_milestone_status(
    COUNT(*) FILTER (WHERE p.word_index_milestone = 'done'),
    COUNT(*) FILTER (WHERE p.word_index_milestone IN ('failed', 'error')),
    COUNT(*) FILTER (WHERE p.word_index_milestone = 'in_progress'),
    COUNT(*)
  )
  FROM pages p
  WHERE p.book_id = b.id
);

-- Backfill Spell Check milestone
UPDATE books b
SET spell_check_milestone = (
  SELECT compute_milestone_status(
    COUNT(*) FILTER (WHERE p.spell_check_milestone = 'done'),
    COUNT(*) FILTER (WHERE p.spell_check_milestone IN ('failed', 'error')),
    COUNT(*) FILTER (WHERE p.spell_check_milestone = 'in_progress'),
    COUNT(*)
  )
  FROM pages p
  WHERE p.book_id = b.id
);

-- Drop the helper function as it's no longer needed
DROP FUNCTION compute_milestone_status(BIGINT, BIGINT, BIGINT, BIGINT);

COMMENT ON COLUMN books.ocr_milestone IS 'Book-level OCR milestone status (denormalized from pages)';
COMMENT ON COLUMN books.chunking_milestone IS 'Book-level chunking milestone status (denormalized from pages)';
COMMENT ON COLUMN books.embedding_milestone IS 'Book-level embedding milestone status (denormalized from pages)';
COMMENT ON COLUMN books.word_index_milestone IS 'Book-level word index milestone status (denormalized from pages)';
COMMENT ON COLUMN books.spell_check_milestone IS 'Book-level spell check milestone status (denormalized from pages)';
