-- Migration 073: Soft-delete support for conversations
ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ NULL;

DROP INDEX IF EXISTS idx_conv_user;

CREATE INDEX IF NOT EXISTS idx_conv_user_active ON conversations (user_id, updated_at DESC)
WHERE
    deleted_at IS NULL;
