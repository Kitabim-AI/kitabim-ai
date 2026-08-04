-- Migration 082: Seed history_extraction_enabled system config
--
-- Inserts the default history_extraction_enabled config row if it does not exist.

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'history_extraction_enabled',
    'true',
    'Globally enable/disable Uyghur history dictionary term extraction feature. Set to ''true'' to enable or ''false'' to disable.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;
