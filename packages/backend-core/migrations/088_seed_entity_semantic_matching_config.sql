-- Migration 088: Seed entity semantic-matching config
--
-- Feature-gates the semantic (embedding-based) candidate source and scoring term in
-- entity resolution (knowledge-graph-improvement-backlog.md Item 8). Defaults to off
-- so behavior is unchanged until explicitly enabled and validated via
-- scripts/eval_entity_semantic_matching.py.

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'entity_semantic_matching_enabled',
    'false',
    'Gate for embedding-based semantic candidate matching in entity resolution (knowledge-graph-improvement-backlog.md Item 8). "true" to enable; also gates whether entity profile embeddings are generated during extraction.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'entity_semantic_weight',
    '0.15',
    'Weight (0.0-1.0) given to profile-embedding cosine similarity in the entity-resolution graded score, when entity_semantic_matching_enabled is true. The remaining weight is distributed proportionally across the existing name/neighbor/subtype signals.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'entity_semantic_candidate_limit',
    '5',
    'Max semantic-similarity candidates fetched per entity from the Neo4j vector index during resolution, in addition to the existing fulltext candidates.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;
