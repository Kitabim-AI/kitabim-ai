-- Rollback 073: Remove soft-delete support for conversations
DROP INDEX IF EXISTS idx_conv_user_active;

CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations (user_id, updated_at DESC);

ALTER TABLE conversations DROP COLUMN IF EXISTS deleted_at;
