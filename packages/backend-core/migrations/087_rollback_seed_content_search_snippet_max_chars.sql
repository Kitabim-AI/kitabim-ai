-- Rollback Migration 087: Delete content_search_snippet_max_chars system config

DELETE FROM system_configs WHERE key = 'content_search_snippet_max_chars';
