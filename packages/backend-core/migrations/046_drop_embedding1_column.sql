-- Drop the embedding1 column from any table that has it.
-- Uses IF EXISTS on each ALTER so this is safe to re-run.

BEGIN;

ALTER TABLE chunks        DROP COLUMN IF EXISTS embedding1;
ALTER TABLE pages         DROP COLUMN IF EXISTS embedding1;
ALTER TABLE book_summaries DROP COLUMN IF EXISTS embedding1;

COMMIT;
