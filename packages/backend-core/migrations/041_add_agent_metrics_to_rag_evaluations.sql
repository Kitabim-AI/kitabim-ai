-- Phase 2: add agentic RAG evaluation columns to rag_evaluations.
-- All columns are nullable so existing rows (standard RAG path) are unaffected.
ALTER TABLE rag_evaluations
    ADD COLUMN agent_steps        INTEGER,
    ADD COLUMN tools_called       TEXT[],
    ADD COLUMN retry_count        INTEGER,
    ADD COLUMN final_chunk_count  INTEGER;
