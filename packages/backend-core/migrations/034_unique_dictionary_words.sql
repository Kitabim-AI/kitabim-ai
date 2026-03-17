-- Migration 034: Add unique index to dictionary.word
-- This migration ensures that words in the dictionary are unique.
-- It also cleans up any existing duplicates by keeping the one with the lowest ID.

BEGIN;

-- 1. Identify and delete duplicates (keeping the first occurrence)
DELETE FROM dictionary a USING (
      SELECT MIN(id) as min_id, word
      FROM dictionary
      GROUP BY word
      HAVING COUNT(*) > 1
    ) b
WHERE a.word = b.word
AND a.id > b.min_id;

-- 2. Add the unique constraint/index
ALTER TABLE dictionary DROP CONSTRAINT IF EXISTS dictionary_word_key;
ALTER TABLE dictionary ADD CONSTRAINT dictionary_word_key UNIQUE (word);

-- 3. Ensure ID is auto-incremental
-- This creates a sequence and attaches it to the ID column if not already managed by SERIAL/IDENTITY
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c 
        JOIN pg_depend d ON c.oid = d.objid 
        JOIN pg_attribute a ON d.refobjid = a.attrelid AND d.refobjsubid = a.attnum
        WHERE c.relkind = 'S' 
        AND a.attname = 'id' 
        AND a.attrelid = 'dictionary'::regclass
    ) THEN
        CREATE SEQUENCE IF NOT EXISTS dictionary_id_seq;
        ALTER TABLE dictionary ALTER COLUMN id SET DEFAULT nextval('dictionary_id_seq');
        ALTER SEQUENCE dictionary_id_seq OWNED BY dictionary.id;
        -- Set sequence to current max ID to avoid collisions
        PERFORM setval('dictionary_id_seq', COALESCE((SELECT MAX(id) FROM dictionary), 0) + 1);
    END IF;
END $$;

COMMIT;
