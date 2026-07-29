-- Rollback 075: Remove entity resolution coordination tables

BEGIN;

DELETE FROM system_configs WHERE key IN (
    'resolution_batch_size',
    'resolution_max_passes',
    'resolution_similarity_threshold',
    'gemini_entity_resolution_model'
);

DROP TABLE IF EXISTS graph_merge_log;
DROP TABLE IF EXISTS graph_resolution_reviews;
DROP TABLE IF EXISTS graph_resolution_queue;

COMMIT;
