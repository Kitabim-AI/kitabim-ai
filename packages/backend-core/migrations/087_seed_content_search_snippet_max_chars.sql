-- Migration 087: Seed content_search_snippet_max_chars system config
--
-- Inserts default content_search_snippet_max_chars config row if it does not exist.

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'content_search_snippet_max_chars',
    '500',
    'Maximum character length of content search result snippets displayed in the Home ''Content'' search tab.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;
