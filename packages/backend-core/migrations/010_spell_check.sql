-- Migration 010: Dictionary-based spell check infrastructure.

-- Enable trigram extension for fuzzy word matching (suggestions)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Deduplicate words table before creating unique index (keep lowest id per word)
DELETE FROM words
WHERE id NOT IN (
    SELECT MIN(id) FROM words GROUP BY word
);

-- Index words table for fast exact lookup and fuzzy matching
CREATE UNIQUE INDEX IF NOT EXISTS idx_words_word ON words(word);
CREATE INDEX IF NOT EXISTS idx_words_trgm ON words USING GIN(word gin_trgm_ops);

-- Track spell check progress per page (independent of OCR/embedding pipeline)
ALTER TABLE pages
    ADD COLUMN IF NOT EXISTS spell_check_milestone TEXT DEFAULT 'idle'
        CHECK (spell_check_milestone IN ('idle', 'in_progress', 'done', 'skipped', 'error'));

-- Store detected spell issues per page
CREATE TABLE IF NOT EXISTS page_spell_issues (
    id          SERIAL PRIMARY KEY,
    page_id     INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    word        TEXT NOT NULL,
    char_offset INTEGER,
    char_end    INTEGER,
    suggestions TEXT[] NOT NULL DEFAULT '{}',
    status      TEXT NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'corrected', 'ignored')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_spell_issues_page   ON page_spell_issues(page_id);
CREATE INDEX IF NOT EXISTS idx_spell_issues_open   ON page_spell_issues(page_id) WHERE status = 'open';
