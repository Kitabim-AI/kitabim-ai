-- Migration 070 Rollback: Drop batch_ocr_jobs table

DROP TABLE IF EXISTS batch_ocr_jobs CASCADE;
