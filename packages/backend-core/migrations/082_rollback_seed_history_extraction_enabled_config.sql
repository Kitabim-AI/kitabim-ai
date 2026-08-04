-- Rollback migration 082: Delete history_extraction_enabled from system_configs

DELETE FROM system_configs WHERE key = 'history_extraction_enabled';
