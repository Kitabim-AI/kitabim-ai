"""Database seeding logic"""

import logging
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.observability import log_json

logger = logging.getLogger("app.db.seeds")


async def seed_system_configs(session: AsyncSession):
    """Seed default system configurations if they don't exist"""
    repo = SystemConfigsRepository(session)

    defaults = [
        {
            "key": "ocr_max_retry_count",
            "value": "10",
            "description": "Maximum number of OCR retry attempts per page before marking it as error/skipped.",
        },
        {
            "key": "gemini_chat_model",
            "value": "gemini-3.1-flash-lite",
            "description": "Gemini model used for chat responses (reader chat and global chat).",
        },
        {
            "key": "gemini_ocr_model",
            "value": "gemini-3.5-flash",
            "description": "Gemini model used for OCR page processing.",
        },
        {
            "key": "gemini_batch_ocr_enabled",
            "value": "false",
            "description": "Globally enable/disable Gemini Batch API for OCR page processing. Set to 'true' to use Batch API (50% cost discount) or 'false' for online real-time OCR.",
        },
        {
            "key": "gemini_batch_ocr_batch_size",
            "value": "50",
            "description": "Maximum number of pages bundled into a single Gemini Batch API job.",
        },
        {
            "key": "gemini_batch_ocr_timeout_hours",
            "value": "24",
            "description": "Hours after which a pending/running Gemini Batch API OCR job is considered timed out and marked stale for retry.",
        },
        {
            "key": "gemini_embedding_model",
            "value": "gemini-embedding-2",
            "description": "Gemini model used for generating text embeddings (vector search).",
        },
        {
            "key": "maintenance_retention_days",
            "value": "7",
            "description": "Number of days to retain processed pipeline events before automated cleanup.",
        },
        {
            "key": "spell_check_enabled",
            "value": "true",
            "description": "Globally enable/disable background spell check processing.",
        },
        {
            "key": "ocr_max_parallel_pages",
            "value": "1",
            "description": "Maximum number of pages to OCR concurrently within a single OCR job. Set to 1 to process pages strictly one at a time.",
        },
        {
            "key": "summary_scanner_batch_size",
            "value": "5",
            "description": "Number of books the summary scanner enqueues per run. Increase temporarily to speed up bulk regeneration, then reset to 5.",
        },
        {
            "key": "graph_scanner_batch_size",
            "value": "5",
            "description": "Number of books the graph scanner enqueues per run. Increase temporarily to speed up bulk backfill, then reset to 5.",
        },
        {
            "key": "gemini_kg_extraction_model",
            "value": "gemini-3.1-flash-lite",
            "description": "Gemini model used for entity/relation extraction during knowledge graph indexing.",
        },
        {
            "key": "kg_chunk_batch_size",
            "value": "5",
            "description": "Number of chunks combined into a single LLM call during knowledge graph extraction. Higher values reduce API calls and improve coreference resolution at the cost of larger prompts. Default tuned for 1500-char chunks (~7 500 chars per call).",
        },
        {
            "key": "kg_max_parallel_chunks",
            "value": "5",
            "description": "Maximum number of concurrent LLM batch calls during knowledge graph extraction. Each call processes kg_chunk_batch_size chunks.",
        },
        {
            "key": "knowledge_graph_enabled",
            "value": "false",
            "description": "Globally enable/disable knowledge graph extraction and the graph scanner. Set to 'true' to activate.",
        },
        {
            "key": "fictional_categories",
            "value": "رومان, تارىخىي رومان, بالىلار رومانى, ساتىرىك رومان, پەلسەپىۋىي رومان, پوۋېست, پوۋېستلار, تارىخىي پوۋېست, ھېكايىلەر, تارىخىي ھېكايىلەر, بالىلار ھېكايىلېرى, چۆچەكلەر, قىسسە, تارىخىي قىسسە, داستان, داستانلار, تارىخىي داستان, رىۋايەتلەر, مەسەللەر, لەتىپىلەر, يۇمۇرلار, شېئىرلار, سەھنە ئەسەرلېرى, كىنو سېنارىيىلىرى",
            "description": "Comma-separated list of categories that indicate a book is fictional. If a book's categories match any in this list, its Person entities will be namespaced to prevent cross-book duplication. Otherwise, it defaults to non-fictional.",
        },
        {
            "key": "ocr_scanner_batch_size",
            "value": "10",
            "description": "Maximum number of pages claimed and processed in a single OCR job batch.",
        },
        {
            "key": "gemini_ocr_timeout",
            "value": "300",
            "description": "Timeout in seconds for Gemini OCR vision API calls.",
        },
        {
            "key": "gemini_chat_timeout",
            "value": "60",
            "description": "Timeout in seconds for Gemini chat/text generation API calls.",
        },
        {
            "key": "gemini_embed_timeout",
            "value": "15",
            "description": "Timeout in seconds for Gemini vector embedding API calls.",
        },
        {
            "key": "gemini_batch_embedding_enabled",
            "value": "false",
            "description": "Globally enable/disable Gemini Batch API embedding processing. Set to 'true' to activate.",
        },
        {
            "key": "log_level",
            "value": "INFO",
            "description": "Global application logging level (DEBUG, INFO, WARNING, ERROR). Configurable dynamically in the System Configs admin panel.",
        },
        {
            "key": "gemini_batch_embedding_timeout_hours",
            "value": "24",
            "description": "Timeout threshold in hours after which a pending/running batch embedding job is marked stale and retried.",
        },
        {
            "key": "history_extraction_enabled",
            "value": "true",
            "description": "Globally enable/disable Uyghur history dictionary term extraction feature. Set to 'true' to enable or 'false' to disable.",
        },
        {
            "key": "history_extraction_model",
            "value": "gemini-2.5-flash",
            "description": "Gemini model used for structured Uyghur history dictionary term extraction and factual synthesis.",
        },
        {
            "key": "gemini_batch_history_extraction_enabled",
            "value": "false",
            "description": "Globally enable/disable Gemini Batch API for history dictionary extraction. Set to 'true' to use Batch API (50% cost discount) or 'false' for online sliding-window extraction.",
        },
        {
            "key": "history_extraction_batch_size",
            "value": "15",
            "description": "Number of book pages grouped per sliding window / batch request during history dictionary extraction.",
        },
        {
            "key": "gemini_batch_embedding_max_chunks_per_job",
            "value": "100",
            "description": "Maximum number of chunks packaged into a single Gemini Batch API embedding submission. Sized for the Tier 1 batch enqueued-tokens budget (500K) assuming several concurrent jobs — raise if the Gemini API key is upgraded to a higher tier.",
        },
        {
            "key": "gemini_batch_embedding_max_retry_count",
            "value": "3",
            "description": "Per-chunk retry ceiling before a failing chunk is skipped during batch embedding ingestion.",
        },
        {
            "key": "rag_judge_scoring_enabled",
            "value": "true",
            "description": "Globally enable/disable async LLM-judge scoring (faithfulness/answer_relevance/context_precision) of RAG chat turns. Set to 'false' to skip scoring and worker dispatch entirely.",
        },
        {
            "key": "gemini_judge_model",
            "value": "gemini-3.1-flash-lite",
            "description": "Gemini model used for the RAG answer-quality judge (faithfulness/answer_relevance/context_precision scoring).",
        },
        {
            "key": "rag_reranker_enabled",
            "value": "true",
            "description": "Globally enable/disable LLM-based reranking of retrieved chunks. Adds one Gemini call to the live chat request path. Set to 'false' to fall back to the relative-score grading heuristic (_grade_context) with zero behavior change.",
        },
        {
            "key": "gemini_reranker_model",
            "value": "gemini-3.1-flash-lite",
            "description": "Gemini model used for LLM-based reranking of retrieved chunks.",
        },
        {
            "key": "rag_vector_top_k",
            "value": "25",
            "description": "Maximum number of top chunks retrieved during vector similarity search and retained for answer context synthesis. Renamed from rag_top_k — see rag_keyword_top_k / rag_graph_top_k for the other two legs' independent caps.",
        },
        {
            "key": "rag_keyword_top_k",
            "value": "10",
            "description": "Maximum number of chunks returned by the keyword (exact-phrase) retrieval leg. Independent of rag_vector_top_k — bounds the keyword leg even for a common phrase.",
        },
        {
            "key": "rag_graph_top_k",
            "value": "10",
            "description": "Maximum number of knowledge-graph facts fed into RAG context per turn, highest-scoring first.",
        },
        {
            "key": "rag_agent_max_llm_calls",
            "value": "12",
            "description": "Hard ceiling on ADK LLM calls per retrieval-agent run (google.adk.RunConfig.max_llm_calls), enforced by the ADK runner itself. AGENT_SYSTEM_PROMPT already asks the model to stop within 6 tool calls (10 for multi-sub-question turns), but that's prose the model can ignore; this is the code-enforced backstop. Set above the prompt's own budget (tool calls + 1 final no-tool-call round) so it only catches genuine runaway loops, not normal completions. When the limit is hit mid-run, the orchestrator logs a warning and proceeds to answer synthesis with whatever evidence was gathered so far, rather than failing the turn.",
        },
        {
            "key": "collection_page_size",
            "value": "40",
            "description": "Batch size for infinite-scroll pagination on the library shelves and home search results.",
        },
        {
            "key": "content_search_snippet_max_chars",
            "value": "500",
            "description": "Maximum character length of content search result snippets displayed in the Home 'Content' search tab.",
        },
    ]

    for item in defaults:
        existing = await repo.get(item["key"])
        if not existing:
            log_json(
                logger,
                logging.INFO,
                "Seeding system config",
                key=item["key"],
                value=item["value"],
            )
            await repo.create(**item)

    await session.commit()
