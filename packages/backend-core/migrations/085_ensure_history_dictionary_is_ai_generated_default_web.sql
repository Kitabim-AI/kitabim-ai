-- Migration: 085_ensure_history_dictionary_is_ai_generated_default_web.sql
-- Description: Ensure all existing history_dictionary entries are tagged as web (is_ai_generated = FALSE)

UPDATE public.history_dictionary SET is_ai_generated = FALSE WHERE is_ai_generated IS NULL;
