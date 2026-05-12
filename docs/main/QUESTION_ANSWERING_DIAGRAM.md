# Question Answering Pipeline Diagram — v3

Visual representation of the current RAG question answering pipeline after introducing the `rag_fast_handlers_enabled` feature flag.

**Changes from v2:**
- `rag_fast_handlers_enabled` system_config added (default `"false"`) — when off, all 8 keyword-based fast-path handlers are skipped and every query goes directly to `AgentRAGHandler`
- `QueryHandler` base class gains `is_fast_handler: bool = False`; all 8 non-agent handlers set it to `True`
- `HandlerRegistry._select()` skips any handler where `is_fast_handler=True and not ctx.fast_handlers_enabled`
- `QueryContext` gains `fast_handlers_enabled: bool = False`, resolved from `system_configs` in `_build_context()` (Redis-cached via `cache_ttl_system_config`)
- No handler logic or tool set changed — fast handlers are fully intact and re-activate the moment the flag is set to `"true"`

**Changes from v1 (carried forward):**
- `StandardRAGHandler` removed from registry (agent is now the sole fallback)
- `CatalogHandler` removed from registry — converted to `search_catalog` agent tool
- `AuthorByTitleHandler` and `BooksByAuthorHandler` kept as fast-path handlers (priority 20/21) **and** exposed as agent tools for compound queries
- `FollowUpHandler` and `CurrentVolumeHandler` now delegate to `AgentRAGHandler`
- Three new agent tools: `get_book_author`, `get_books_by_author`, `search_catalog`
- `context_builder` accumulates both metadata context (catalog/author tools) and chunk context
- `AGENT_MAX_CONTEXT_CHUNKS = 15` cap applied after score-sort
- LLM "categorize question" call eliminated entirely
- `FollowUpHandler` now also detects the "چۇ" topic-shift clitic ("what about X?") as heuristic 3
- Context injection: agent's first message includes `[Context]` block (current book, context book IDs, category filter) — agent skips book-discovery step when book is known
- `rewrite_query` tool short-circuits when `ctx.enriched_question` is already set (pre-rewritten by `FollowUpHandler`)

---

## Full Pipeline

```mermaid
flowchart TD
    %% Entry
    Q([User Question\n+ Chat History\n+ Context]) --> BUILD

    %% Context build — reads flag once per request
    subgraph ContextBuild [_build_context — rag_service.py]
        BUILD[Resolve character, models\nread system_configs]
        BUILD --> FLAG_READ[(system_configs\nrag_fast_handlers_enabled\ndefault: false\ncached in Redis)]
        FLAG_READ --> CTX[QueryContext\nfast_handlers_enabled = bool]
    end

    CTX --> REG

    %% Handler Registry
    subgraph Registry [HandlerRegistry._select — priority-ordered]
        REG{fast_handlers_enabled?}

        REG -->|false — default\nskip all is_fast_handler=True| H_AG[AgentRAGHandler\npriority=998]

        REG -->|true — evaluate each\nhandler in order| FAST_PATH{Intent\nmatching}
        FAST_PATH -->|Identity / greeting| H_ID[IdentityHandler\npriority=10\nis_fast_handler=True]
        FAST_PATH -->|Capability question| H_CAP[CapabilityHandler\npriority=11\nis_fast_handler=True]
        FAST_PATH -->|Author keywords — who wrote X?| H_ABT[AuthorByTitleHandler\npriority=20\nis_fast_handler=True]
        FAST_PATH -->|Author keywords — what did Y write?| H_BBA[BooksByAuthorHandler\npriority=21\nis_fast_handler=True]
        FAST_PATH -->|Volume / page count info| H_VOL[VolumeInfoHandler\npriority=22\nis_fast_handler=True]
        FAST_PATH -->|Follow-up markers, pronouns,\nor چۇ particle| H_FU[FollowUpHandler\npriority=30\nis_fast_handler=True]
        FAST_PATH -->|In-reader, current page| H_CP[CurrentPageHandler\npriority=40\nis_fast_handler=True]
        FAST_PATH -->|In-reader, current volume| H_CV[CurrentVolumeHandler\npriority=41\nis_fast_handler=True]
        FAST_PATH -->|No fast handler matched| H_AG
    end

    %% Simple handlers exit immediately
    H_ID --> ANS
    H_CAP --> ANS
    H_ABT -->|Title match found| ANS
    H_ABT -->|No match| H_AG
    H_BBA -->|Author match found| ANS
    H_BBA -->|No match| H_AG
    H_VOL -->|Title match found| ANS
    H_VOL -->|No match — falls back to CatalogHandler| ANS_GEN

    %% Follow-Up path
    subgraph FollowUp [FollowUpHandler]
        H_FU --> QR[QueryRewriter]
        QR -->|Cache hit| QR_CACHE[(Rewrite Cache\nKEY_RAG_REWRITE)]
        QR -->|Cache miss| QR_LLM[LLM: resolve pronouns\noutput standalone question]
        QR_LLM --> QR_CACHE
        QR_CACHE --> ENRICH[ctx.enriched_question set]
        ENRICH -->|delegate| H_AG
    end

    %% CurrentPage path
    subgraph CurrentPage [CurrentPageHandler]
        H_CP --> PAGE_FETCH[(PagesRepository\ncurrent page text)]
        PAGE_FETCH --> PAGE_CTX[Page text as context]
    end
    PAGE_CTX --> ANS_GEN

    %% CurrentVolume path
    H_CV -->|set use_current_volume_only=True\nthen delegate| H_AG

    %% Agentic RAG — main path
    subgraph AgentRAG [AgentRAGHandler — ReAct Loop]
        H_AG --> CTX_INJ[_build_human_message\nInject Context block:\ncurrent book_id, context book IDs,\ncategory filter]
        CTX_INJ --> AG_LOOP[ReAct Loop\nmax 4 steps]

        subgraph Loop [Agentic Loop — repeats until chunks ≥ 8 or max steps reached]
            AG_LOOP --> AG_LLM[LLM tool-calling invocation\nAgent model]
            AG_LLM -->|No tool calls| DONE[Loop ends —\nsufficient context]
            AG_LLM -->|Tool calls| AG_TOOLS{Dispatch\ntools in parallel}

            subgraph ContentTools [Content Retrieval]
                AG_TOOLS -->|search_chunks| T_CHUNKS[pgvector similarity search\nL1 + L2 cache]
                AG_TOOLS -->|search_books_by_summary| T_SUMM[Summary embedding search\nL3 cache]
                AG_TOOLS -->|find_books_by_title| T_TITLE[Title match\nDB lookup]
                AG_TOOLS -->|rewrite_query| T_REWRITE[Short-circuit if already rewritten\notherwise resolve co-references — L0 cache]
            end

            subgraph MetadataTools [Catalog & Metadata]
                AG_TOOLS -->|get_book_author| T_AUTHOR[Author lookup\nBooksRepository]
                AG_TOOLS -->|get_books_by_author| T_BOOKS[Books by author\nBooksRepository]
                AG_TOOLS -->|search_catalog| T_CAT[Catalog context\ntitle → author → full listing]
            end

            T_CHUNKS & T_SUMM & T_TITLE & T_REWRITE & T_AUTHOR & T_BOOKS & T_CAT --> AG_OBS[Accumulate\nObservations]
            AG_OBS -->|chunks < 8 and steps < 4| AG_LOOP
        end

        DONE & AG_OBS --> CTX_BUILD

        subgraph ContextBuilder [format_observations_as_context]
            CTX_BUILD[Collect all observations]
            CTX_BUILD --> META[Metadata context\nfrom catalog/author tools\nin call order]
            CTX_BUILD --> CHUNK_DEDUP[Chunks from search_chunks\ndeduplicate by book_id + page\nsort by score DESC\ncap at 15]
            META & CHUNK_DEDUP --> COMBINED[Combined context string\npassed to answer LLM]
        end
    end

    %% Answer Generation
    COMBINED --> ANS_GEN

    subgraph AnswerGen [Answer Generation — final LLM call]
        ANS_GEN[Context + question\n+ chat history] --> ANS_LLM[RAG Chain\nLLM: generate answer]
        ANS_LLM -->|Streaming| STREAM[Stream tokens to client]
        ANS_LLM -->|Non-streaming| FULL[Full response]
    end

    STREAM --> ANS([Answer delivered to user])
    FULL --> ANS

    classDef handler fill:#e9edc9,stroke:#606c38,stroke-width:2px
    classDef cache fill:#ffe8d6,stroke:#b5838d,stroke-dasharray: 5 5
    classDef llm fill:#d4f1f4,stroke:#189ab4,stroke-width:1px
    classDef decision fill:#fef9c3,stroke:#854d0e,stroke-width:1px
    classDef store fill:#f0e6ff,stroke:#7c3aed,stroke-width:1px
    classDef newtool fill:#dcfce7,stroke:#16a34a,stroke-width:2px
    classDef inject fill:#fce7f3,stroke:#be185d,stroke-width:2px
    classDef flag fill:#fff7ed,stroke:#ea580c,stroke-width:2px

    class H_ID,H_CAP,H_ABT,H_BBA,H_VOL,H_FU,H_CP,H_CV,H_AG handler
    class QR_CACHE,QR_LLM llm
    class T_AUTHOR,T_BOOKS,T_CAT newtool
    class CTX_INJ inject
    class AG_TOOLS,REG,FAST_PATH decision
    class PAGE_FETCH store
    class FLAG_READ flag
```

---

## Handler Routing Reference

```mermaid
flowchart LR
    Q([Question]) --> FLAG

    FLAG{rag_fast_handlers_enabled\n= true?}
    FLAG -->|No — default| RAGENT[AgentRAGHandler\nReAct loop — 7 tools]

    FLAG -->|Yes| P1
    P1{Identity /\ngreeting?} -->|Yes| R1[IdentityHandler\nDirect reply]
    P1 -->|No| P2
    P2{Capability\nquestion?} -->|Yes| R2[CapabilityHandler\nDirect reply]
    P2 -->|No| P3
    P3{Author\nkeywords —\nwho wrote X?} -->|Yes| R3[AuthorByTitleHandler\nDB lookup → direct reply\nor → AgentRAG on miss]
    P3 -->|No| P4
    P4{Author\nkeywords —\nwhat did Y write?} -->|Yes| R4[BooksByAuthorHandler\nDB lookup → direct reply\nor → AgentRAG on miss]
    P4 -->|No| P5
    P5{Volume /\npage count?} -->|Yes| R5[VolumeInfoHandler\nDB lookup → direct reply]
    P5 -->|No| P6
    P6{Follow-up markers,\npronouns, or\nچۇ particle?} -->|Yes| R6[FollowUpHandler\n→ rewrite → AgentRAG]
    P6 -->|No| P7
    P7{In-reader:\ncurrent page?} -->|Yes| R7[CurrentPageHandler\nPage text → answer]
    P7 -->|No| P8
    P8{In-reader:\ncurrent volume?} -->|Yes| R8[CurrentVolumeHandler\nset scope flag → AgentRAG]
    P8 -->|No| RAGENT
```

---

## Agentic Retrieval Strategy

This diagram illustrates the agent's internal decision tree for tool selection, governed entirely by the `AGENT_SYSTEM_PROMPT`.

```mermaid
flowchart TD
    Q([User Question]) --> CTX[Agent Checks Context & Question]

    CTX -->|Pronouns / چۇ particle\n+ Chat history| REWRITE[Tool: rewrite_query]
    REWRITE --> CTX

    CTX -->|Metadata / Catalog Intent| METADATA
    CTX -->|Content / Passage Intent| CONTENT

    subgraph Metadata Strategy
        METADATA -->|who wrote title?| T_GET_AUTH[Tool: get_book_author]
        METADATA -->|what did author write?| T_GET_BOOKS[Tool: get_books_by_author]
        METADATA -->|general library browsing| T_CAT[Tool: search_catalog]
    end

    subgraph Content Strategy
        CONTENT -->|Specific book:\nPlot/Characters/Themes| T_TITLE_SUMM[Tool: find_books_by_title]
        T_TITLE_SUMM -->|IDs| T_GET_SUMM[Tool: get_book_summary]

        CONTENT -->|Specific book:\nDetails/Passages| T_TITLE[Tool: find_books_by_title]
        T_TITLE -->|IDs| T_CHUNKS_TITLE[Tool: search_chunks]

        CONTENT -->|Names author| T_AUTHOR[Tool: get_books_by_author]
        T_AUTHOR -->|IDs| T_CHUNKS_AUTH[Tool: search_chunks]

        CONTENT -->|Context: current book| T_CHUNKS_CTX[Tool: search_chunks\nwith known book_ids]
        CONTENT -->|Context: previous books| T_CHUNKS_CTX

        CONTENT -->|No Context/Title/Author\nor General Theme| T_SUMM[Tool: search_books_by_summary]
        T_SUMM -->|IDs| T_CHUNKS_SUMM[Tool: search_chunks]

        T_CHUNKS_CTX & T_CHUNKS_TITLE & T_CHUNKS_AUTH & T_CHUNKS_SUMM --> CHK{Passages < 4?}
        CHK -->|Yes| T_CHUNKS_ALL[Tool: search_chunks\nempty book_ids = all books]
        CHK -->|No| DONE
    end

    T_GET_AUTH & T_GET_BOOKS & T_CAT & T_GET_SUMM & T_CHUNKS_ALL --> DONE

    DONE([Stop: Issue no tool calls\nto signal completion])

    classDef tool fill:#dcfce7,stroke:#16a34a,stroke-width:2px
    classDef decision fill:#fef9c3,stroke:#854d0e,stroke-width:1px
    
    class REWRITE,T_GET_AUTH,T_GET_BOOKS,T_CAT,T_CHUNKS_CTX,T_TITLE,T_TITLE_SUMM,T_CHUNKS_TITLE,T_GET_SUMM,T_AUTHOR,T_CHUNKS_AUTH,T_SUMM,T_CHUNKS_SUMM,T_CHUNKS_ALL tool
    class CTX,METADATA,CONTENT,CHK decision
```

---

## Agent Tools Reference

| Tool | Type | Wraps | When agent calls it |
|------|------|-------|---------------------|
| `rewrite_query` | Utility | `QueryRewriter` | Question has pronouns or "چۇ" particle and chat history exists; short-circuits if already rewritten by `FollowUpHandler` |
| `find_books_by_title` | Content | `BooksRepository` title match | Question explicitly names a book title and no book_id in `[Context]` |
| `search_books_by_summary` | Content | `BookSummariesRepository` | Finding which books cover a topic; skipped when `[Context]` provides book IDs |
| `search_chunks` | Content | pgvector similarity search | Retrieving passages; uses L1+L2 cache; called directly with `[Context]` book_id when available |
| `get_book_author` | Metadata | `BooksRepository` | All author queries when `rag_fast_handlers_enabled=false`; compound queries when flag is on |
| `get_books_by_author` | Metadata | `BooksRepository` | All books-by-author queries when flag is off; compound queries when flag is on |
| `search_catalog` | Metadata | `CatalogHandler._build_catalog_context` | Library browsing, listing, general catalog questions |

---

## Cache Layers

| Level | Key | Populated By | Purpose |
|-------|-----|-------------|---------|
| **L0** | `KEY_RAG_REWRITE` | `rewrite_query` tool / FollowUpHandler | Deduplicate follow-up rewrites |
| **L1** | `KEY_RAG_EMBEDDING` | First embed call per query | Reuse embeddings across all tools |
| **L2** | `KEY_RAG_SEARCH_SINGLE/MULTI` | `search_chunks` tool | Reuse pgvector search results |
| **L3** | `KEY_RAG_SUMMARY_SEARCH` | `search_books_by_summary` tool | Reuse book-selection results |
| **config** | `config:rag_fast_handlers_enabled` | `SystemConfigsRepository.get_value` | Avoids DB hit on every request; invalidated by `set_value` |

---

## LLM Calls (in execution order)

| # | Call | Triggered By | Condition | Purpose |
|---|------|-------------|-----------|---------|
| 1 | Query rewrite | FollowUpHandler | Follow-up detected **and** `rag_fast_handlers_enabled=true` | Resolve pronouns → standalone question |
| 2 | Agent ReAct loop (1–4×) | AgentRAGHandler | Always — every query when flag is off; unmatched intents when flag is on | Tool-calling loop — choose and invoke retrieval tools |
| 3 | Answer generation | AgentRAGHandler (final) | Always | Generate answer from accumulated context |

> **Removed vs v1:** LLM call "Categorize question" (StandardRAGHandler) no longer exists.

---

## Key Components

| Component | Role |
|-----------|------|
| **HandlerRegistry** | Evaluates `can_handle()` in priority order; skips handlers where `is_fast_handler=True` when `ctx.fast_handlers_enabled=False` |
| **QueryHandler.is_fast_handler** | Class-level flag (`False` on base, `True` on all 8 non-agent handlers); used by registry to apply the feature gate |
| **QueryContext.fast_handlers_enabled** | Resolved from `system_configs` once per request in `_build_context()`; gates all fast handlers |
| **QueryRewriter** | LLM-based standalone question generator; resolves pronouns using conversation history |
| **AuthorByTitleHandler** | Fast path for "who wrote X?" — keyword detect + DB lookup, zero agent calls; falls back to AgentRAG on miss; gated by feature flag |
| **BooksByAuthorHandler** | Fast path for "list books by Y" — keyword detect + DB lookup, zero agent calls; falls back to AgentRAG on miss; gated by feature flag |
| **FollowUpHandler** | Detects follow-up signals (markers, pronouns, "چۇ" clitic); rewrites question via LLM; delegates to AgentRAG; gated by feature flag |
| **AgentRAGHandler** | Handles every query when flag is off (`is_fast_handler=False`, never skipped); fallback for unmatched intents when flag is on; injects `[Context]` block; runs ReAct loop with 7 tools |
| **_build_human_message** | Enriches the agent's first HumanMessage with current book_id, context book IDs, and category filter; enables agent to skip book-discovery step |
| **format_observations_as_context** | Combines metadata context (catalog/author tools) + deduplicated, score-sorted chunks (cap 15) |
| **AnswerBuilder** | Formats chunks into LangChain documents; invokes final RAG chain (streaming or batch) |
| **retrieval.py** | Shared I/O primitives (`embed_query`, `vector_search`, `find_books_by_title_in_question`) used by agent tools |
| **agent/config.py** | Centralized ReAct loop magic numbers (`AGENT_MAX_STEPS`, `AGENT_ENOUGH_CHUNKS`, `AGENT_MAX_CONTEXT_CHUNKS`) |
| **ChunksRepository** | pgvector `similarity_search` against `chunks` table |
| **BookSummariesRepository** | pgvector `summary_search` against `book_summaries` for book selection |
| **CatalogHandler** | Utility class (not in registry); used by `search_catalog` tool and VolumeInfoHandler fallback |
| **QueryContext** | Mutable dataclass threaded through the pipeline; accumulates enriched question, vector, book IDs, scores, agent metrics, and `fast_handlers_enabled` flag |

---

## Feature Flag Reference

| Config key | Table | Default | Effect when `"true"` |
|------------|-------|---------|----------------------|
| `rag_fast_handlers_enabled` | `system_configs` | `"false"` | Enables all 8 keyword-based fast-path handlers in priority order before the agent fallback |

To enable: `UPDATE system_configs SET value = 'true' WHERE key = 'rag_fast_handlers_enabled';`
Change propagates within `cache_ttl_system_config` seconds — no restart required.
