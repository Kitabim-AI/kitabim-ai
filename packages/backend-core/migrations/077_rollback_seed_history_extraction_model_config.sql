-- Rollback migration 077: Delete history_extraction_model from system_config

DELETE FROM system_config WHERE key = 'history_extraction_model';
