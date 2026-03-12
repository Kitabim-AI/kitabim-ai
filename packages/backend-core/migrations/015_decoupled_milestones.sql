-- Migration: Decoupled Pipeline Milestones and Transactional Outbox
-- Reason: Decouples sequential pipeline steps and enables event-driven processing

-- 1. Create pipeline_events table
CREATE TABLE IF NOT EXISTS pipeline_events (
    id SERIAL PRIMARY KEY,
    page_id INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    payload TEXT,
    processed BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pipeline_events_page_id ON pipeline_events(page_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_events_processed ON pipeline_events(processed) WHERE processed = FALSE;

-- 2. Add new milestone columns to pages
ALTER TABLE pages 
ADD COLUMN IF NOT EXISTS ocr_milestone VARCHAR(20) DEFAULT 'idle' NOT NULL,
ADD COLUMN IF NOT EXISTS chunking_milestone VARCHAR(20) DEFAULT 'idle' NOT NULL,
ADD COLUMN IF NOT EXISTS embedding_milestone VARCHAR(20) DEFAULT 'idle' NOT NULL;

-- 3. Retrofit existing data
-- ocr_milestone
UPDATE pages SET ocr_milestone = 'succeeded' 
WHERE pipeline_step IN ('chunking', 'embedding', 'indexed') OR (pipeline_step = 'ocr' AND milestone = 'succeeded');

UPDATE pages SET ocr_milestone = 'failed' 
WHERE pipeline_step = 'ocr' AND milestone = 'failed';

-- chunking_milestone
UPDATE pages SET chunking_milestone = 'succeeded' 
WHERE pipeline_step IN ('embedding', 'indexed') OR (pipeline_step = 'chunking' AND milestone = 'succeeded');

UPDATE pages SET chunking_milestone = 'failed' 
WHERE pipeline_step = 'chunking' AND milestone = 'failed';

-- embedding_milestone
UPDATE pages SET embedding_milestone = 'succeeded' 
WHERE pipeline_step = 'indexed' OR (pipeline_step = 'embedding' AND milestone = 'succeeded');

UPDATE pages SET embedding_milestone = 'failed' 
WHERE pipeline_step = 'embedding' AND milestone = 'failed';

-- 4. Cleanup/Sync word_index_milestone (optional, but good for consistency)
-- If we previously reset everything for the word count retrofit, they should already be 'idle'.
-- If a page is already indexed, and word_index_milestone is idle, it's ready for pick up.

-- 5. Add comments
COMMENT ON COLUMN pages.ocr_milestone IS 'Milestone for the OCR stage';
COMMENT ON COLUMN pages.chunking_milestone IS 'Milestone for the text chunking stage';
COMMENT ON COLUMN pages.embedding_milestone IS 'Milestone for the vector embedding stage';
COMMENT ON TABLE pipeline_events IS 'Transactional outbox for pipeline state transitions and event-driven triggers';
