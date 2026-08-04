-- Migration: 081_add_trgm_index_on_history_dictionary_definition.sql
-- Description: Add GIN trigram index on definition column in history_dictionary for keyword search
-- Author: Omarjan
-- Date: 2026-08-04

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_history_dictionary_def_trgm
    ON public.history_dictionary USING gin (definition public.gin_trgm_ops);

COMMIT;
