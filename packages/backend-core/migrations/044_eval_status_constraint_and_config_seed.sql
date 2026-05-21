-- Migration 044: eval_status CHECK constraint + rag_eval_enabled seed
-- Author: Antigravity
-- Date: 2026-05-20
--
-- 1. Adds a CHECK constraint on rag_evaluations.eval_status so only known
--    values are accepted. Includes 'failed' for eval jobs that exhaust retries.
--
-- 2. Seeds rag_eval_enabled = 'false' so operators can see the config key
--    exists and know to flip it to 'true' to activate background evaluation.
--    The default remains off so new deployments are not surprised by eval load.

BEGIN;

-- Back-fill any legacy 'pending' rows (created before _record_eval was added)
-- to 'skipped' so they don't violate the new constraint.
UPDATE rag_evaluations
SET eval_status = 'skipped'
WHERE eval_status = 'pending';

ALTER TABLE rag_evaluations
    ALTER COLUMN eval_status SET DEFAULT 'skipped',
    ADD CONSTRAINT rag_evaluations_eval_status_check
    CHECK (eval_status IN ('queued', 'skipped', 'completed', 'failed'));

-- Seed the feature-flag config key if not already present.
-- Set to 'false' by default — flip to 'true' in system_configs to enable.
INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'rag_eval_enabled',
    'false',
    'Enable background Ragas semantic evaluation of RAG responses. '
    'Set to ''true'' to activate; see also rag_eval_sampling_rate.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

COMMIT;
