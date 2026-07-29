-- Migration: 075_add_entity_resolution_tables.sql
-- Description: Knowledge Graph Entity Resolution v2 — coordination tables for the
--              Neo4j global resolution queue, admin review queue, and merge audit log.
--              See docs/feature/rag-retrieval-reranking-hybrid-search/knowledge-graph-entity-resolution-design-v2.md
-- Author: Claude
-- Date: 2026-07-28

BEGIN;

-- graph_resolution_queue: coordinates claiming of Neo4j entities for resolution.
-- Postgres owns queue state (FOR UPDATE SKIP LOCKED); Neo4j owns entity data.
CREATE TABLE IF NOT EXISTS graph_resolution_queue (
    id              SERIAL PRIMARY KEY,
    entity_id       UUID NOT NULL,
    scope           TEXT NOT NULL CHECK (scope IN ('fiction', 'nonfiction')),
    book_id         TEXT REFERENCES books(id) ON DELETE CASCADE,
    sort_year       INTEGER,
    status          TEXT NOT NULL DEFAULT 'idle'
        CHECK (status IN ('idle', 'in_progress', 'succeeded', 'failed', 'needs_review')),
    pass_count      INTEGER NOT NULL DEFAULT 0,
    last_updated    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (entity_id)
);
CREATE INDEX IF NOT EXISTS graph_resolution_queue_status_idx ON graph_resolution_queue (status);
CREATE INDEX IF NOT EXISTS graph_resolution_queue_sort_idx ON graph_resolution_queue (scope, sort_year);

-- graph_resolution_reviews: admin review queue for gray-zone / ambiguous resolution outcomes.
CREATE TABLE IF NOT EXISTS graph_resolution_reviews (
    id              SERIAL PRIMARY KEY,
    entity_a_id     UUID NOT NULL,
    entity_b_id     UUID NOT NULL,
    scope           TEXT NOT NULL CHECK (scope IN ('fiction', 'nonfiction')),
    evidence        JSONB NOT NULL,
    suggested_action TEXT NOT NULL CHECK (suggested_action IN ('merge', 'split', 'unsure')),
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewed_by     TEXT REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS graph_resolution_reviews_status_idx ON graph_resolution_reviews (status);

-- graph_merge_log: pre-merge snapshot of the removed node + its edges, enabling unmerge.
CREATE TABLE IF NOT EXISTS graph_merge_log (
    id                       SERIAL PRIMARY KEY,
    kept_entity_id           UUID NOT NULL,
    removed_entity_id        UUID NOT NULL,
    removed_entity_snapshot  JSONB NOT NULL,
    removed_edges_snapshot   JSONB NOT NULL,
    performed_by             TEXT,
    performed_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    reverted_at              TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS graph_merge_log_removed_entity_idx ON graph_merge_log (removed_entity_id);

-- Seed tuneable config for the resolution scanner/job and its gray-zone LLM judge.
INSERT INTO system_configs (key, value, description, updated_at) VALUES
    ('resolution_batch_size', '20',
     'Rows claimed from graph_resolution_queue per graph_resolution_scanner tick.', NOW()),
    ('resolution_max_passes', '5',
     'Max re-propagation passes for one entity before it is force-marked needs_review.', NOW()),
    ('resolution_similarity_threshold', '2',
     'Max Lucene fuzzy edit-distance used against entity_search_idx for candidate matching.', NOW()),
    ('gemini_entity_resolution_model', 'gemini-3.1-flash-lite',
     'Gemini model used for the gray-zone entity-resolution judge call.', NOW())
ON CONFLICT (key) DO NOTHING;

COMMIT;
