-- Migration: 086_add_aliases_to_history_dictionary.sql
-- Description: Add aliases column to history_dictionary and history_dictionary_staging tables

ALTER TABLE public.history_dictionary ADD COLUMN IF NOT EXISTS aliases JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE public.history_dictionary_staging ADD COLUMN IF NOT EXISTS aliases JSONB NOT NULL DEFAULT '[]'::jsonb;
