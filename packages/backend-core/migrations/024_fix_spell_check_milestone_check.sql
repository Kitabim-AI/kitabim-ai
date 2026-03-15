-- Migration: Update spell_check_milestone check constraint
-- Description: Adds 'failed' to the allowed values for spell_check_milestone to match other scanners and avoid IntegrityErrors.

ALTER TABLE pages DROP CONSTRAINT IF EXISTS pages_spell_check_milestone_check;

ALTER TABLE pages ADD CONSTRAINT pages_spell_check_milestone_check 
CHECK (spell_check_milestone IN ('idle', 'in_progress', 'done', 'skipped', 'failed', 'error'));
