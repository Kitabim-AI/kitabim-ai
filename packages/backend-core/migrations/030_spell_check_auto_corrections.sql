-- Migration 030: Auto-correction system for spell check issues.
--
-- Allows admins to define correction rules (misspelled → corrected) and
-- automatically apply them via a background job. This reduces manual editing
-- workload for commonly repeated OCR errors or systematic spelling mistakes.

-- Stores correction rules: which misspelled words should be auto-corrected to what.
CREATE TABLE IF NOT EXISTS spell_check_corrections (
    misspelled_word TEXT PRIMARY KEY,
    corrected_word  TEXT NOT NULL,
    auto_apply      BOOLEAN NOT NULL DEFAULT false,
    description     TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by      VARCHAR(36) REFERENCES users(id) ON DELETE SET NULL,

    CONSTRAINT different_words CHECK (misspelled_word != corrected_word)
);

-- Index for fast lookups when checking if a correction rule exists
CREATE INDEX IF NOT EXISTS idx_spell_check_corrections_auto_apply
    ON spell_check_corrections(misspelled_word) WHERE auto_apply = true;

-- Track when an issue was auto-corrected (NULL = not auto-corrected)
ALTER TABLE page_spell_issues
    ADD COLUMN IF NOT EXISTS auto_corrected_at TIMESTAMPTZ;

-- Index to find issues that have been auto-corrected
CREATE INDEX IF NOT EXISTS idx_page_spell_issues_auto_corrected
    ON page_spell_issues(auto_corrected_at) WHERE auto_corrected_at IS NOT NULL;

-- Add system config for enabling/disabling auto-correction
INSERT INTO system_configs (key, value, description)
VALUES
    ('auto_correct_enabled', 'false', 'Enable automatic spell check corrections'),
    ('auto_correct_batch_size', '50', 'Maximum number of pages to auto-correct per job')
ON CONFLICT (key) DO NOTHING;
