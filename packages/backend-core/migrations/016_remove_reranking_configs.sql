-- Migration: Remove reranking system configs
-- Created: 2026-03-13
-- Description: Deletes rag_rerank_enabled and rag_rerank_top_n from system_configs table.

DELETE FROM system_configs
WHERE key IN ('rag_rerank_enabled', 'rag_rerank_top_n');
