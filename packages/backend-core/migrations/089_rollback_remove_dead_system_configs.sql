-- Rollback Migration 089: Restore dead system_configs rows
--
-- Re-inserts the 11 rows deleted by 089_remove_dead_system_configs.sql, with
-- the values/descriptions they held in production at deletion time. None of
-- these are read by any code path — this rollback exists only in case a
-- prior deploy still depends on the row being present (e.g. an in-flight
-- rollback of the ADK-chat consolidation itself).

BEGIN;

INSERT INTO system_configs (key, value, description, updated_at) VALUES
(
    'use_adk_chat_v2',
    'true',
    'Enable ADK Chat v2 and server-side chat history',
    NOW()
),
(
    'use_deterministic_router',
    'false',
    $d$Globally enable/disable the deterministic Python RAG router instead of the LLM-driven ADK ReAct agent. Set to 'true' to activate.$d$,
    NOW()
),
(
    'rag_eval_enabled',
    'true',
    'Enable RAG query evaluation recording',
    NOW()
),
(
    'agent_max_steps',
    '6',
    'Maximum ReAct iterations/steps per round in the agent loop.',
    NOW()
),
(
    'agent_enough_chunks',
    '8',
    'Early-exit threshold: stop agent loop once this many chunks are collected.',
    NOW()
),
(
    'rag_top_k',
    '25',
    'Maximum number of top chunks retrieved during vector/hybrid search and retained for answer context synthesis.',
    NOW()
),
(
    'rag_hybrid_search_enabled',
    'true',
    $d$Globally enable/disable the Postgres full-text keyword search leg fused with vector search (Reciprocal Rank Fusion). Set to 'false' for vector-only retrieval, identical to pre-hybrid-search behavior.$d$,
    NOW()
),
(
    'gemini_embedding_model_v2',
    'models/gemini-embedding-2',
    'Gemini Embedding v2 model used during migration to 3072-dim embeddings. Verify model ID before enabling reembedding_scanner.',
    NOW()
),
(
    'gemini_batch_ocr_poll_interval',
    '120',
    'Interval in seconds between poller scanner checks for running Gemini Batch API OCR jobs.',
    NOW()
),
(
    'fictional_categories',
    $d$رومان, تارىخىي رومان, بالىلار رومانى, ساتىرىك رومان, پەلسەپىۋىي رومان, پوۋېست, پوۋېستلار, تارىخىي پوۋېست, ھېكايىلەر, تارىخىي ھېكايىلەر, بالىلار ھېكايىلېرى, چۆچەكلەر, قىسسە, تارىخىي قىسسە, داستان, داستانلار, تارىخىي داستان, رىۋايەتلەر, مەسەللەر, لەتىپىلەر, يۇمۇرلار, شېئىرلار, سەھنە ئەسەرلېرى, كىنو سېنارىيىلىرى$d$,
    $d$Comma-separated list of categories that indicate a book is fictional. If a book's categories match any in this list, its Person entities will be namespaced to prevent cross-book duplication. Otherwise, it defaults to non-fictional.$d$,
    NOW()
),
(
    'use_knowledge_graph_in_chat',
    'false',
    NULL,
    NOW()
)
ON CONFLICT (key) DO NOTHING;

COMMIT;
