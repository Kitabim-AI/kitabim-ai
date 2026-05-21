-- Migration 043: Add user_feedback column to rag_evaluations
-- Stores 'positive' (👍) or 'negative' (👎) user ratings per assistant message.
-- NULL means the user has not yet rated that response.

ALTER TABLE rag_evaluations
    ADD COLUMN IF NOT EXISTS user_feedback VARCHAR(10) NULL;

-- Index to efficiently query "all thumbs-down evaluations that need Ragas scoring"
CREATE INDEX IF NOT EXISTS idx_rag_evaluations_user_feedback
    ON rag_evaluations (user_feedback)
    WHERE user_feedback IS NOT NULL;
