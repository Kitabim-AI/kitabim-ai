-- Migration 036: Add claimed_at to page_spell_issues
ALTER TABLE page_spell_issues ADD COLUMN claimed_at TIMESTAMP WITH TIME ZONE;
