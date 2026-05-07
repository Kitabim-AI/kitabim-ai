DROP INDEX CONCURRENTLY IF EXISTS idx_chunks_embedding_v2;
DROP INDEX CONCURRENTLY IF EXISTS idx_book_summaries_embedding_v2;

CREATE INDEX CONCURRENTLY idx_chunks_embedding_v2
  ON chunks USING hnsw ((embedding_v2::halfvec(3072)) halfvec_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX CONCURRENTLY idx_book_summaries_embedding_v2
  ON book_summaries USING ivfflat ((embedding_v2::halfvec(3072)) halfvec_cosine_ops)
  WITH (lists = 50);
