BEGIN;

ALTER TABLE chunks         RENAME COLUMN embedding    TO embedding_v1;
ALTER TABLE chunks         RENAME COLUMN embedding_v2 TO embedding;
ALTER TABLE book_summaries RENAME COLUMN embedding    TO embedding_v1;
ALTER TABLE book_summaries RENAME COLUMN embedding_v2 TO embedding;

ALTER INDEX idx_chunks_embedding              RENAME TO idx_chunks_embedding_v1;
ALTER INDEX idx_chunks_embedding_v2           RENAME TO idx_chunks_embedding;
ALTER INDEX idx_book_summaries_embedding      RENAME TO idx_book_summaries_embedding_v1;
ALTER INDEX idx_book_summaries_embedding_v2   RENAME TO idx_book_summaries_embedding;

UPDATE system_configs
  SET value = 'models/gemini-embedding-2'
  WHERE key = 'gemini_embedding_model';

COMMIT;
