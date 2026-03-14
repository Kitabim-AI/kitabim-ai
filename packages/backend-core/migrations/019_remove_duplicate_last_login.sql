-- Migration: Remove duplicate last_login column (keeping last_login_at)
-- Created at: 2026-03-13
-- Description: The users table had both 'last_login' and 'last_login_at' columns.
--              All application code uses 'last_login_at', so we're dropping the duplicate 'last_login'.

-- Drop the duplicate last_login column
ALTER TABLE users DROP COLUMN IF EXISTS last_login;
