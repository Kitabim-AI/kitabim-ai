-- Migration 078: Add batch_history_extraction_jobs table for Gemini Batch API history extraction processing

CREATE TABLE IF NOT EXISTS batch_history_extraction_jobs (
    id VARCHAR(64) PRIMARY KEY,
    gemini_batch_id VARCHAR(255) UNIQUE,
    book_id VARCHAR(64) NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'submitting',
    gcs_input_uri TEXT,
    gcs_output_uri TEXT,
    total_batches INT NOT NULL DEFAULT 0,
    min_significance INT NOT NULL DEFAULT 5,
    model_name VARCHAR(100) NOT NULL DEFAULT 'gemini-2.5-flash',
    error TEXT,
    submitted_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_batch_history_jobs_status CHECK (
        status IN ('submitting', 'submitted', 'running', 'succeeded', 'failed', 'cancelled')
    )
);

CREATE INDEX IF NOT EXISTS idx_batch_history_jobs_book_id ON batch_history_extraction_jobs(book_id);
CREATE INDEX IF NOT EXISTS idx_batch_history_jobs_status ON batch_history_extraction_jobs(status);

INSERT INTO system_configs (key, value, description)
VALUES (
    'gemini_batch_history_extraction_enabled',
    'false',
    'Enable Gemini Batch API for history dictionary extraction (true/false)'
) ON CONFLICT (key) DO NOTHING;
