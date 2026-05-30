-- Migration 045: Add graph_milestone to books table and seed config
-- Author: Antigravity
-- Date: 2026-05-23
--
-- 1. Adds 'graph_milestone' column to books table to track graph indexing status.
-- 2. Seeds 'knowledge_graph_enabled' system configuration set to 'false' by default.

BEGIN;

-- Add graph_milestone column if it does not exist
ALTER TABLE books
    ADD COLUMN IF NOT EXISTS graph_milestone VARCHAR(20) DEFAULT 'idle' NOT NULL;

-- Seed system configuration for enabling/disabling Knowledge Graph
INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'knowledge_graph_enabled',
    'false',
    'Enable background Knowledge Graph entity/relationship extraction and indexing. '
    'Set to ''true'' to activate; set to ''false'' to disable. Defaults to ''false''.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

COMMIT;
