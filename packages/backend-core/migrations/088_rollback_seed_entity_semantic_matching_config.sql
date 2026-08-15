-- Rollback Migration 088: Delete entity semantic-matching config

DELETE FROM system_configs WHERE key = 'entity_semantic_matching_enabled';
DELETE FROM system_configs WHERE key = 'entity_semantic_weight';
DELETE FROM system_configs WHERE key = 'entity_semantic_candidate_limit';
