-- Migration: Add index on proverbs text column
-- Description: Improves search performance for proverbs.

-- Standard B-tree index for exact matches and sorting
CREATE INDEX IF NOT EXISTS idx_proverbs_text ON proverbs (text);

-- GIN trigram index for fuzzy/substring search (Uyghur text search)
CREATE INDEX IF NOT EXISTS idx_proverbs_text_trgm ON proverbs USING gin (text gin_trgm_ops);
