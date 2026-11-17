# Chat Orchestration Service (`app/services/chat`)

## Overview
Coordinates conversational AI queries over Uyghur literary works, managing query analysis, catalog shortcuts, exact phrase lookups, agentic retrieval, context grading, and persona-aligned answer synthesis.

## Interface
- `[orchestrator.py:ChatOrchestrator]` — Primary coordinator handling end-to-end chat requests, routing between catalog lookups, exact phrase retrieval, and full agentic RAG.
- `[context.py:ChatRequestDTO]` — Data transfer object holding request context, user identity, conversation history, and scope boundaries.
- `[context.py:ToolDependencies]` — Dependency container providing repository and service references to retrieval tools.
- `[query_signals.py:analyze_query_signals]` — `analyze_query_signals(...)`: Analyzes query intents (catalog, author, content, page reference, entity search).
- `[query_signals.py:repair_json_unescaped_quotes]` — Utility fixing malformed JSON quotes returned by LLM classification.
- `[exact_phrase.py:run_exact_phrase_retrieval]` — Direct search for exact text phrases across book pages, forwarding section and printed-page metadata.
- `[context_grading.py:_grade_context]` — Filters, deduplicates by `(book_id, page, section_id)`, and grades candidate text chunks for query relevance before final answer construction.
- `[retrieval_agent.py:build_retrieval_agent]` — Assembles the multi-step agentic retrieval LangChain workflow.
- `[retrieval_agent.py:ALL_TOOLS]` — Complete registry of tools accessible to the retrieval agent.
- `[answer_agent.py:build_answer_agent]` — Assembles the final answer synthesis agent.
- `[answer_prompts.py:build_answer_instructions]` — Constructs persona instructions, volume constraints, and citation formatting directives.
- `[history.py:format_history_for_analysis]` — Formats conversation history turns for LLM query reformulation.

## Invariants
- `[orchestrator.py:ChatOrchestrator]` — Bypasses multi-step agent retrieval for catalog queries and direct book lookups using catalog shortcuts.
- `[answer_prompts.py:build_answer_instructions]` — Answers must strictly adhere to provided factual context and cite source books and page numbers.
- `[exact_phrase.py:run_exact_phrase_retrieval]` — Restricts phrase search scope to specified books when scope constraints are present.

## Side Effects
- Makes LLM generation calls to Gemini for query analysis, tool execution, and final answer generation.
- Reads and updates chat usage quotas in Redis.
- Records RAG evaluations, token usages, and costs in PostgreSQL.

## Verification
- Run: `pytest packages/backend-core/tests`
