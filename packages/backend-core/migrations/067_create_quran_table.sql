-- Migration: 067_create_quran_table.sql
-- Description: Create quran table for storing Surahs and Ayahs
-- Author: Omarjan
-- Date: 2026-07-05

BEGIN;

CREATE TABLE IF NOT EXISTS public.quran (
    id            SERIAL PRIMARY KEY,
    surah         INTEGER NOT NULL,
    surah_name_en VARCHAR(255) NOT NULL,
    surah_name_ar VARCHAR(255) NOT NULL,
    surah_name_ug VARCHAR(255) NOT NULL,
    ayah          INTEGER NOT NULL,
    text_ar       TEXT NOT NULL,
    text_en       TEXT NOT NULL,
    text_ug       TEXT NOT NULL,
    created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

-- Index for searching ayahs by surah
CREATE INDEX IF NOT EXISTS idx_quran_surah ON public.quran (surah);

-- Compound unique constraint for surah & ayah to prevent duplicate verses
CREATE UNIQUE INDEX IF NOT EXISTS idx_quran_surah_ayah ON public.quran (surah, ayah);

-- GIN trigram indices for searching texts in multiple languages
CREATE INDEX IF NOT EXISTS idx_quran_text_ug_trgm ON public.quran USING gin (text_ug public.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_quran_text_en_trgm ON public.quran USING gin (text_en public.gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_quran_text_ar_trgm ON public.quran USING gin (text_ar public.gin_trgm_ops);

COMMIT;
