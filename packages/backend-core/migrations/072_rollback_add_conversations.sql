-- Rollback 072: Drop conversations and conversation_messages tables
DROP INDEX IF EXISTS idx_eval_conv;
DROP INDEX IF EXISTS idx_conv_msg;
DROP INDEX IF EXISTS idx_conv_user;

ALTER TABLE rag_evaluations DROP COLUMN IF EXISTS conversation_id;

DROP TABLE IF EXISTS conversation_messages;
DROP TABLE IF EXISTS conversations;
