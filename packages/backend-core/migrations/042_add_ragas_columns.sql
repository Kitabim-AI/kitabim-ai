-- Migration: 042_add_ragas_columns.sql
-- Description: Add Ragas evaluation score columns, answer/context fields, and seed configurations
-- Author: Antigravity
-- Date: 2026-05-20

BEGIN;

-- Add evaluation columns
ALTER TABLE rag_evaluations
    ADD COLUMN faithfulness_score      FLOAT NULL,
    ADD COLUMN answer_relevance_score  FLOAT NULL,
    ADD COLUMN context_precision_score FLOAT NULL,
    ADD COLUMN context_recall_score    FLOAT NULL,
    ADD COLUMN eval_status             VARCHAR(20) DEFAULT 'skipped' NOT NULL,
    ADD COLUMN answer                  TEXT NULL,
    ADD COLUMN retrieved_context       TEXT NULL;

-- Seed system configuration defaults
INSERT INTO system_configs (key, value, description, updated_at)
VALUES 
    ('gemini_eval_model', 'gemini-3-flash-preview', 'Gemini model used for RAG semantic evaluations (needs Uyghur support)', NOW()),
    ('rag_eval_sampling_rate', '0.05', 'Fraction of production queries asynchronously evaluated using Ragas (0.00 to 1.00)', NOW())
ON CONFLICT (key) DO UPDATE 
SET value = EXCLUDED.value, description = EXCLUDED.description, updated_at = NOW();

COMMIT;
