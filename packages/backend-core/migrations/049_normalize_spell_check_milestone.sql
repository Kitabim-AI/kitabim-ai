-- Normalize pages.spell_check_milestone: replace 'done' with 'succeeded'
-- to match the value used by all other pipeline steps (ocr, chunking, embedding).
--
-- Also updates the CHECK constraint to remove 'done' and add 'succeeded'.
-- 'skipped' is retained in the constraint as a reserved future state.

-- 1. Drop the old constraint first (it allows 'done' but not 'succeeded')
ALTER TABLE pages DROP CONSTRAINT pages_spell_check_milestone_check;

-- 2. Migrate existing data
UPDATE pages
SET spell_check_milestone = 'succeeded'
WHERE spell_check_milestone = 'done';

-- 3. Add the new constraint
ALTER TABLE pages ADD CONSTRAINT pages_spell_check_milestone_check
    CHECK (spell_check_milestone = ANY (ARRAY[
        'idle', 'in_progress', 'succeeded', 'skipped', 'failed', 'error'
    ]));
