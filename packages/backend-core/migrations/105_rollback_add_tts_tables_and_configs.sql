-- Rollback: 105_rollback_add_tts_tables_and_configs.sql
-- Description: Drop tts_audio_cache and user_tts_usage tables and remove TTS system_configs.

BEGIN;

DELETE FROM system_configs
WHERE key IN (
    'tts_enabled',
    'tts_gemini_model',
    'tts_default_voice',
    'tts_default_style',
    'tts_gemini_timeout',
    'tts_max_chars',
    'tts_limit_reader',
    'tts_limit_editor'
);

DROP TABLE IF EXISTS user_tts_usage;
DROP TABLE IF EXISTS tts_audio_cache;

COMMIT;
