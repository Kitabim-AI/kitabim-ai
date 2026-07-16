ALTER TABLE rag_evaluations
    ADD COLUMN IF NOT EXISTS is_first_turn BOOLEAN NOT NULL DEFAULT false;
