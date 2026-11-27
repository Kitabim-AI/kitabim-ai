-- Migration: 105_add_tts_tables_and_configs.sql
-- Description: Add tts_audio_cache and user_tts_usage tables and seed TTS system_configs
--              for Gemini-based Q&A answer text-to-speech (Global & Reader chat).
-- Author: Kitabim.AI
-- Date: 2026-11-25

BEGIN;

CREATE TABLE IF NOT EXISTS tts_audio_cache (
    content_hash      VARCHAR(64) PRIMARY KEY,
    storage_path      TEXT NOT NULL,
    mime_type         VARCHAR(64) NOT NULL DEFAULT 'audio/mpeg',
    model             VARCHAR(100) NOT NULL,
    voice             VARCHAR(100) NOT NULL,
    style             TEXT NOT NULL DEFAULT '',
    text_chars        INTEGER NOT NULL DEFAULT 0,
    duration_sec      DOUBLE PRECISION NULL,
    size_bytes        INTEGER NOT NULL DEFAULT 0,
    input_tokens      INTEGER NOT NULL DEFAULT 0,
    output_tokens     INTEGER NOT NULL DEFAULT 0,
    cost_usd          NUMERIC(12, 6) NOT NULL DEFAULT 0,
    hit_count         INTEGER NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_accessed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tts_audio_cache_last_accessed
    ON tts_audio_cache (last_accessed_at);

CREATE TABLE IF NOT EXISTS user_tts_usage (
    id          SERIAL PRIMARY KEY,
    user_id     VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    usage_date  DATE NOT NULL DEFAULT CURRENT_DATE,
    count       INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT user_tts_usage_user_id_date_key UNIQUE (user_id, usage_date)
);

CREATE INDEX IF NOT EXISTS idx_user_tts_usage_user_id ON user_tts_usage (user_id);
CREATE INDEX IF NOT EXISTS idx_user_tts_usage_date ON user_tts_usage (usage_date);

INSERT INTO system_configs (key, value, description, updated_at)
VALUES
    (
        'tts_enabled',
        'true',
        'Globally enable/disable Gemini TTS audio playback for question answers in Global and Reader chat (true/false).',
        NOW()
    ),
    (
        'tts_gemini_model',
        'gemini-3.8-flash-tts',
        'Gemini TTS model used for synthesizing question answers. Required for Uyghur support (no fallback).',
        NOW()
    ),
    (
        'tts_default_voice',
        'Sadaltager',
        'Default Gemini TTS prebuilt voice name (or custom voice_... ID) used for question answer narration.',
        NOW()
    ),
    (
        'tts_default_style',
        'calm, clear, articulate narrator',
        'English speech_metadata.style delivery instruction passed to Gemini TTS.',
        NOW()
    ),
    (
        'tts_gemini_timeout',
        '90',
        'Timeout in seconds for Gemini TTS streaming API calls.',
        NOW()
    ),
    (
        'tts_max_chars',
        '5000',
        'Maximum normalized character length synthesized per question answer.',
        NOW()
    ),
    (
        'tts_limit_reader',
        '15',
        'Daily uncached TTS synthesis limit for reader role (cached replays are free and unlimited).',
        NOW()
    ),
    (
        'tts_limit_editor',
        '50',
        'Daily uncached TTS synthesis limit for editor role (cached replays are free and unlimited; admin is unlimited).',
        NOW()
    )
ON CONFLICT (key) DO NOTHING;

COMMIT;
