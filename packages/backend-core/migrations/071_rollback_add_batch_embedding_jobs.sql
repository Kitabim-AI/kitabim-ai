-- Migration 071 Rollback: Drop batch_embedding_jobs table

DROP TABLE IF EXISTS batch_embedding_jobs CASCADE;
