DELETE FROM system_configs
WHERE key IN (
    'pdf_processing_enabled',
    'llm_cb_failure_threshold',
    'llm_cb_recovery_seconds',
    'batch_polling_interval_minutes',
    'batch_last_polled_at',
    'batch_ocr_limit',
    'batch_embedding_limit',
    'batch_chunking_limit',
    'batch_books_per_submission',
    'batch_ocr_retry_after',
    'batch_submission_interval_minutes',
    'batch_submission_last_run_at'
);
