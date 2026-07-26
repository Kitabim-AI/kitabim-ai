-- Migration 072: Add conversations and conversation_messages tables, and link rag_evaluations
CREATE TABLE IF NOT EXISTS conversations (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    book_id VARCHAR(64) REFERENCES books (id) ON DELETE SET NULL,
    is_global BOOLEAN NOT NULL DEFAULT FALSE,
    title VARCHAR(200),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id VARCHAR(36) PRIMARY KEY,
    conversation_id VARCHAR(36) NOT NULL REFERENCES conversations (id) ON DELETE CASCADE,
    role VARCHAR(10) NOT NULL,
    content TEXT NOT NULL,
    agent_steps JSONB,
    used_book_ids JSONB,
    current_page INTEGER,
    eval_id INTEGER REFERENCES rag_evaluations (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_conversation_messages_role CHECK (role IN ('user', 'model'))
);

ALTER TABLE rag_evaluations
ADD COLUMN IF NOT EXISTS conversation_id VARCHAR(36) REFERENCES conversations (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations (user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_conv_msg ON conversation_messages (conversation_id, created_at);

CREATE INDEX IF NOT EXISTS idx_eval_conv ON rag_evaluations (conversation_id);

INSERT INTO
    system_configs (key, value, description)
VALUES (
        'use_adk_chat_v2',
        'true',
        'Enable ADK v2 server-side chat history'
    ) ON CONFLICT (key) DO
UPDATE
SET
    value = 'true';