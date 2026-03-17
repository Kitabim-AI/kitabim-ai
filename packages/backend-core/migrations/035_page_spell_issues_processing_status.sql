-- Migration 035: Add 'processing' status to page_spell_issues
-- This allows the auto-correction job to claim issues and avoid parallel processing.

ALTER TABLE page_spell_issues DROP CONSTRAINT page_spell_issues_status_check;
ALTER TABLE page_spell_issues ADD CONSTRAINT page_spell_issues_status_check 
    CHECK (status IN ('open', 'corrected', 'ignored', 'processing'));
