-- Migration 077: Seed history_extraction_model system config
--
-- Inserts the default history_extraction_model config row if it does not exist.

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'history_extraction_model',
    'gemini-2.5-flash',
    'Gemini model used for structured Uyghur history dictionary term extraction and factual synthesis.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;
