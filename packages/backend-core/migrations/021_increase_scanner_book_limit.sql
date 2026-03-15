-- Migration: Increase scanner book limit for faster pipeline processing
-- Created: 2026-03-14
-- Description: Increase scanner_book_limit from 10 to 20 for 2x more books queued per scan
--              This is a safe optimization with zero data corruption risk.

-- Update or insert the scanner_book_limit config
INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'scanner_book_limit',
    '20',
    'Maximum number of books to process per scanner run',
    NOW()
)
ON CONFLICT (key)
DO UPDATE SET
    value = '20',
    updated_at = NOW();
