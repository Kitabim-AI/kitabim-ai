-- Migration 011: Replace suggestions with ocr_corrections in page_spell_issues.
-- Only OCR character-substitution corrections are stored (e.g. ك→ڭ, و→ۇ, ه→ھ).

ALTER TABLE page_spell_issues
    ADD COLUMN IF NOT EXISTS ocr_corrections TEXT[] NOT NULL DEFAULT '{}';

ALTER TABLE page_spell_issues
    DROP COLUMN IF EXISTS suggestions;

-- Clear all existing spell check data so pages are re-scanned with new logic.
DELETE FROM page_spell_issues;

UPDATE pages
    SET spell_check_milestone = 'idle'
    WHERE spell_check_milestone IS NOT NULL
      AND spell_check_milestone != 'idle';
