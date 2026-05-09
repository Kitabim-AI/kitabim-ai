# Question Answering Pipeline Diagram — v2

Visual representation of the current RAG question answering pipeline after agentic RAG promotion and handler consolidation.

**Changes from v1:**
- `StandardRAGHandler` removed from registry (agent is now the sole fallback)
- `CatalogHandler` removed from registry — converted to `search_catalog` agent tool
- `AuthorByTitleHandler` and `BooksByAuthorHandler` kept as fast-path handlers (priority 20/21) **and** exposed as agent tools for compound queries
- `FollowUpHandler` and `CurrentVolumeHandler` now delegate to `AgentRAGHandler`
- Three new agent tools: `get_book_author`, `get_books_by_author`, `search_catalog`
- `context_builder` accumulates both metadata context (catalog/author tools) and chunk context
- `MAX_CONTEXT_CHUNKS = 15` cap applied after score-sort
- LLM "categorize question" call eliminated entirely

---

## Full Pipeline

```mermaid
flowchart TD
    %% Entry
    Q([User Question\n+ Chat History\n+ Context]) --> REG

    %% Handler Registry
    subgraph Registry [HandlerRegistry — first match wins, ordered by priority]
        REG{Intent\nClassification}
        REG -->|Identity / greeting| H_ID[IdentityHandler]
        REG -->|Capability question| H_CAP[CapabilityHandler]
        REG -->|Author keywords — who wrote X?| H_ABT[AuthorByTitleHandler\npriority=20]
        REG -->|Author keywords — what did Y write?| H_BBA[BooksByAuthorHandler\npriority=21]
        REG -->|Volume / page count info| H_VOL[VolumeInfoHandler\npriority=22]
        REG -->|Contains follow-up\nmarkers or pronouns| H_FU[FollowUpHandler\npriority=30]
        REG -->|In-reader, current page| H_CP[CurrentPageHandler\npriority=40]
        REG -->|In-reader, current volume| H_CV[CurrentVolumeHandler\npriority=41]
        REG -->|Everything else| H_AG[AgentRAGHandler\npriority=998]
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
        H_AG --> AG_LOOP[ReAct Loop\nmax 4 steps]

        subgraph Loop [Agentic Loop — repeats until chunks ≥ 8 or max steps reached]
            AG_LOOP --> AG_LLM[LLM tool-calling invocation\nAgent model]
            AG_LLM -->|No tool calls| DONE[Loop ends —\nsufficient context]
            AG_LLM -->|Tool calls| AG_TOOLS{Dispatch\ntools in parallel}

            subgraph ContentTools [Content Retrieval]
                AG_TOOLS -->|search_chunks| T_CHUNKS[pgvector similarity search\nL1 + L2 cache]
                AG_TOOLS -->|search_books_by_summary| T_SUMM[Summary embedding search\nL3 cache]
                AG_TOOLS -->|find_books_by_title| T_TITLE[Title match\nDB lookup]
                AG_TOOLS -->|rewrite_query| T_REWRITE[Resolve co-references\nL0 cache]
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

    class H_ID,H_CAP,H_ABT,H_BBA,H_VOL,H_FU,H_CP,H_CV,H_AG handler
    class QR_CACHE,QR_LLM llm
    class T_AUTHOR,T_BOOKS,T_CAT newtool
    class AG_TOOLS,REG decision
    class PAGE_FETCH store
```

---

## Handler Routing Reference

```mermaid
flowchart LR
    Q([Question]) --> P1
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
    P6{Follow-up\nmarkers or\npronouns?} -->|Yes| R6[FollowUpHandler\n→ rewrite → AgentRAG]
    P6 -->|No| P7
    P7{In-reader:\ncurrent page?} -->|Yes| R7[CurrentPageHandler\nPage text → answer]
    P7 -->|No| P8
    P8{In-reader:\ncurrent volume?} -->|Yes| R8[CurrentVolumeHandler\nset scope flag → AgentRAG]
    P8 -->|No| R9[AgentRAGHandler\nReAct loop — 7 tools]
```

---

## Agent Tools Reference

| Tool | Type | Wraps | When agent calls it |
|------|------|-------|---------------------|
| `rewrite_query` | Utility | `QueryRewriter` | Question has Uyghur pronouns and chat history exists |
| `find_books_by_title` | Content | `BooksRepository` title match | Question explicitly names a book title |
| `search_books_by_summary` | Content | `BookSummariesRepository` | Finding which books cover a topic before chunk search |
| `search_chunks` | Content | pgvector similarity search | Retrieving passages; uses L1+L2 cache |
| `get_book_author` | Metadata | `BooksRepository` | Compound queries needing author as a step (fast-path handler handles the simple case) |
| `get_books_by_author` | Metadata | `BooksRepository` | Compound queries needing book list as a step (fast-path handler handles the simple case) |
| `search_catalog` | Metadata | `CatalogHandler._build_catalog_context` | Library browsing, listing, general catalog questions |

---

## Cache Layers

| Level | Key | Populated By | Purpose |
|-------|-----|-------------|---------|
| **L0** | `KEY_RAG_REWRITE` | `rewrite_query` tool / FollowUpHandler | Deduplicate follow-up rewrites |
| **L1** | `KEY_RAG_EMBEDDING` | First embed call per query | Reuse embeddings across all tools |
| **L2** | `KEY_RAG_SEARCH_SINGLE/MULTI` | `search_chunks` tool | Reuse pgvector search results |
| **L3** | `KEY_RAG_SUMMARY_SEARCH` | `search_books_by_summary` tool | Reuse book-selection results |

---

## LLM Calls (in execution order)

| # | Call | Triggered By | Condition | Purpose |
|---|------|-------------|-----------|---------|
| 1 | Query rewrite | FollowUpHandler | Follow-up detected | Resolve pronouns → standalone question |
| 2 | Agent ReAct loop (1–4×) | AgentRAGHandler | Always | Tool-calling loop — choose and invoke retrieval tools |
| 3 | Answer generation | AgentRAGHandler (final) | Always | Generate answer from accumulated context |

> **Removed vs v1:** LLM call #2 "Categorize question" (StandardRAGHandler) no longer exists.

---

## Key Components

| Component | Role |
|-----------|------|
| **HandlerRegistry** | Evaluates `can_handle()` in priority order; dispatches to first match |
| **QueryRewriter** | LLM-based standalone question generator; resolves pronouns using conversation history |
| **AuthorByTitleHandler** | Fast path for "who wrote X?" — keyword detect + DB lookup, zero agent calls; falls back to AgentRAG on miss |
| **BooksByAuthorHandler** | Fast path for "list books by Y" — keyword detect + DB lookup, zero agent calls; falls back to AgentRAG on miss |
| **AgentRAGHandler** | Fallback for all unmatched intents; runs a ReAct loop with 7 tools; always-on |
| **format_observations_as_context** | Combines metadata context (catalog/author tools) + deduplicated, score-sorted chunks (cap 15) |
| **AnswerBuilder** | Formats chunks into LangChain documents; invokes final RAG chain (streaming or batch) |
| **ChunksRepository** | pgvector `similarity_search` against `chunks` table |
| **BookSummariesRepository** | pgvector `summary_search` against `book_summaries` for book selection |
| **CatalogHandler** | Utility class (not in registry); used by `search_catalog` tool and VolumeInfoHandler fallback |
| **StandardRAGHandler** | Utility class (not in registry); used by `search_chunks` and `find_books_by_title` tools |
| **QueryContext** | Mutable dataclass threaded through the pipeline; accumulates enriched question, vector, book IDs, scores, agent metrics |
