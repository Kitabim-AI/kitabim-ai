-- Migration 089: Remove dead system_configs rows
--
-- Deletes 11 system_configs keys with zero remaining readers in the codebase.
--
-- Five are legacy chat-pipeline flags whose only readers were deleted by the
-- ADK-chat consolidation (docs/superpowers/plans/2026-08-12-adk-chat-consolidation.md
-- Task 7): use_adk_chat_v2, use_deterministic_router, rag_eval_enabled,
-- agent_max_steps, agent_enough_chunks.
--
-- The remaining six were found by cross-referencing every system_configs row
-- against every get_value()/get_system_config_timeout() call site:
--   - rag_top_k: renamed to rag_vector_top_k (keyword-search-rework-plan).
--   - rag_hybrid_search_enabled: gated RRF hybrid-fusion code that was deleted;
--     row was deliberately left behind as harmless/unread.
--   - gemini_embedding_model_v2: fed the embedding_v2 columns from the v1->v2
--     migration (migration 035); those columns are unused in current code.
--   - gemini_batch_ocr_poll_interval: never read anywhere, not even seeded in
--     current seeds.py.
--   - fictional_categories: still seeded, but the fictional-Person-namespacing
--     feature it described was never implemented.
--   - use_knowledge_graph_in_chat: no description, not in any seed/migration —
--     added ad hoc via the admin UI, never wired to any code.

BEGIN;

DELETE FROM system_configs WHERE key IN (
    'use_adk_chat_v2',
    'use_deterministic_router',
    'rag_eval_enabled',
    'agent_max_steps',
    'agent_enough_chunks',
    'rag_top_k',
    'rag_hybrid_search_enabled',
    'gemini_embedding_model_v2',
    'gemini_batch_ocr_poll_interval',
    'fictional_categories',
    'use_knowledge_graph_in_chat'
);

COMMIT;
