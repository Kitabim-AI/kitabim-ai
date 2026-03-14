-- Migration: Add index for user chat usage lookup
-- Created: 2026-03-14
-- Description: Adds an index to speed up chat usage lookups by user and date.
-- Note: A unique constraint index already exists on (user_id, usage_date), 
-- but this explicitly names the lookup index.

CREATE INDEX IF NOT EXISTS idx_user_chat_usage_lookup 
ON user_chat_usage(user_id, usage_date);
