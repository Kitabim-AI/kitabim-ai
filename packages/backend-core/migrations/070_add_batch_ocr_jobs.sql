-- Migration 070: Add batch_ocr_jobs table for Gemini Batch API OCR processing

CREATE TABLE IF NOT EXISTS batch_ocr_jobs (
    id VARCHAR(64) PRIMARY KEY,
    gemini_batch_id VARCHAR(255) UNIQUE,
    book_id VARCHAR(64) NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    page_ids INT[] NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'submitting',
    gcs_input_uri TEXT,
    gcs_output_uri TEXT,
    total_pages INT NOT NULL DEFAULT 0,
    processed_pages INT NOT NULL DEFAULT 0,
    error TEXT,
    submitted_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_batch_ocr_jobs_status CHECK (
        status IN ('submitting', 'submitted', 'running', 'succeeded', 'failed', 'cancelled')
    )
);

CREATE INDEX IF NOT EXISTS idx_batch_ocr_jobs_book_id ON batch_ocr_jobs(book_id);
CREATE INDEX IF NOT EXISTS idx_batch_ocr_jobs_status ON batch_ocr_jobs(status);
