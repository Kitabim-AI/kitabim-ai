-- Migration: Add last_login_ip to users table
-- Created at: 2026-03-13

ALTER TABLE users ADD COLUMN last_login_ip VARCHAR(45);
