# Question Answering Pipeline Diagram

Visual representation of the RAG question answering pipeline — from user question to streamed answer — including handler routing, query rewriting, book selection, vector search, agentic loop, and answer generation.

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
        REG -->|Author by title| H_ABT[AuthorByTitleHandler]
        REG -->|Books by author| H_BBA[BooksByAuthorHandler]
        REG -->|Volume / catalog info| H_VOL[VolumeInfoHandler / CatalogHandler]
        REG -->|Contains follow-up\nmarkers or pronouns| H_FU[FollowUpHandler\npriority=30]
        REG -->|agentic_rag_enabled=true| H_AG[AgentRAGHandler\npriority=998]
        REG -->|Everything else| H_STD[StandardRAGHandler\npriority=999]
    end

    %% Simple handlers exit early
    H_ID --> ANS
    H_CAP --> ANS
    H_ABT --> ANS
    H_BBA --> ANS
    H_VOL --> ANS

    %% Follow-Up path
    subgraph FollowUp [Follow-Up Handler]
        H_FU --> QR[QueryRewriter\nLLM Call #1]
        QR -->|Cache L0 hit| QR_CACHE[(Rewrite Cache\nKEY_RAG_REWRITE)]
        QR -->|Cache L0 miss| QR_LLM[LLM: resolve pronouns\noutput standalone question]
        QR_LLM --> QR_CACHE
        QR_CACHE --> ENRICH[ctx.enriched_question set]
        ENRICH -->|delegate| H_STD
    end

    %% Standard RAG path
    subgraph StandardRAG [StandardRAGHandler]
        H_STD --> MODE{Single-book\nor Global?}

        MODE -->|Global| BOOK_SEL[Book Selection]

        subgraph BookSel [Book Selection — Global Mode]
            BOOK_SEL --> CHAR_FILT{Character\ncategory filter?}
            CHAR_FILT -->|Yes| CHAR_BOOKS[(Query books\nby category)]
            CHAR_FILT -->|No| TITLE_MATCH

            CHAR_BOOKS --> TITLE_MATCH{Title mentioned\nin question?}
            TITLE_MATCH -->|Exact or fuzzy match| USE_TITLE[Restrict to\nmatched books]
            TITLE_MATCH -->|No match| SUM_SEARCH[Summary-based\nbook search\nCache L3]
            SUM_SEARCH -->|Cache hit| SUM_CACHE[(Summary Search Cache\nKEY_RAG_SUMMARY_SEARCH)]
            SUM_SEARCH -->|Cache miss| SUM_VEC[Embed question\n→ similarity search\nbook_summaries table]
            SUM_VEC --> SUM_CACHE
            SUM_CACHE --> USE_SUM[Top-N books\nby summary score]
            USE_SUM --> CTX_BOOKS{Frontend context\nbook IDs?}
            CTX_BOOKS -->|Available| USE_CTX[Use ctx.context_book_ids]
            CTX_BOOKS -->|None| CAT_FALL[LLM: categorize question\nLLM Call #2]
            CAT_FALL --> USE_CAT[Books matching\ndetected category]
        end

        MODE -->|Single book| VOL_CHECK{use_current_\nvolume_only?}
        VOL_CHECK -->|Yes| THIS_VOL[Current volume only]
        VOL_CHECK -->|No| SIBLINGS[Current book +\nsibling volumes]

        USE_TITLE --> EMBED
        USE_SUM --> EMBED
        USE_CTX --> EMBED
        USE_CAT --> EMBED
        THIS_VOL --> EMBED
        SIBLINGS --> EMBED

        %% Embedding
        EMBED[Embed enriched question\nCache L1]
        EMBED -->|Cache hit| EMB_CACHE[(Embedding Cache\nKEY_RAG_EMBEDDING)]
        EMBED -->|Cache miss| EMB_LLM[Embeddings model\n.aembed_query]
        EMB_LLM --> EMB_CACHE

        %% Vector search
        EMB_CACHE --> VSEARCH[Vector Search\nCache L2]
        VSEARCH -->|Cache hit| VS_CACHE[(Search Cache\nKEY_RAG_SEARCH_*)]
        VSEARCH -->|Cache miss| VS_DB[(chunks table\npgvector similarity_search\ntop_k, threshold)]
        VS_DB --> VS_CACHE
        VS_CACHE --> CHUNKS[Retrieved Chunks\nwith scores]

        %% Fallback
        CHUNKS -->|Empty| SUM_FALL[Fallback: book summaries\nas context]
        CHUNKS -->|Found| CTX_BUILD[Build context\nformat docs with metadata]
        SUM_FALL --> CTX_BUILD
    end

    %% Agentic RAG path
    subgraph AgentRAG [AgentRAGHandler — ReAct Loop]
        H_AG --> AG_LOOP[ReAct Loop\nmax 4 steps]
        subgraph Loop [Agentic Loop — repeats until enough_chunks ≥ 8 or max steps]
            AG_LOOP --> AG_LLM[LLM tool-calling invocation\nAgent model\nLLM Call #3]
            AG_LLM --> AG_TOOLS{Tool calls\nfrom LLM?}
            AG_TOOLS -->|search_chunks| T_CHUNKS[Vector search\nreuse L1+L2 cache]
            AG_TOOLS -->|search_books_by_summary| T_SUMM[Summary search\nreuse L3 cache]
            AG_TOOLS -->|find_books_by_title| T_TITLE[Title extraction]
            AG_TOOLS -->|rewrite_query| T_REWRITE[Resolve follow-up\nreuse L0 cache]
            T_CHUNKS & T_SUMM & T_TITLE & T_REWRITE -->|parallel| AG_OBS[Accumulate\nObservations]
            AG_OBS --> AG_LOOP
        end
        AG_OBS -->|Loop done| AG_CTX[Format observations\nas context]
    end

    %% Convergence point
    CTX_BUILD --> ANS_GEN[Answer Generation]
    AG_CTX --> ANS_GEN

    %% Answer Generation
    subgraph AnswerGen [Answer Generation — LLM Call #4]
        ANS_GEN --> ANS_LLM[RAG Chain\nLLM: generate answer\nfrom context + history]
        ANS_LLM -->|Streaming| STREAM[Stream chunks\nto client]
        ANS_LLM -->|Non-streaming| FULL[Full response]
    end

    STREAM --> ANS([Answer\ndelivered to user])
    FULL --> ANS

    classDef handler fill:#e9edc9,stroke:#606c38,stroke-width:2px
    classDef cache fill:#ffe8d6,stroke:#b5838d,stroke-dasharray: 5 5
    classDef llm fill:#d4f1f4,stroke:#189ab4,stroke-width:1px
    classDef decision fill:#fef9c3,stroke:#854d0e,stroke-width:1px
    classDef store fill:#f0e6ff,stroke:#7c3aed,stroke-width:1px

    class H_ID,H_CAP,H_ABT,H_BBA,H_VOL,H_FU,H_STD,H_AG handler
    class QR_CACHE,EMB_CACHE,VS_CACHE,SUM_CACHE cache
    class QR_LLM,EMB_LLM,AG_LLM,ANS_LLM,CAT_FALL llm
    class REG,MODE,CHAR_FILT,TITLE_MATCH,CTX_BOOKS,VOL_CHECK,AG_TOOLS decision
    class VS_DB,CHAR_BOOKS store
```

---

## Handler Routing Reference

```mermaid
flowchart LR
    Q([Question]) --> P1
    P1{Identity /\ngreeting?} -->|Yes| R1[IdentityHandler\nDirect LLM reply]
    P1 -->|No| P2
    P2{Capability\nquestion?} -->|Yes| R2[CapabilityHandler\nDirect reply]
    P2 -->|No| P3
    P3{Bibliographic\nquery?} -->|Yes| R3[Author / Volume /\nCatalog Handlers]
    P3 -->|No| P4
    P4{Follow-up\nmarkers or\npronouns?} -->|Yes| R4[FollowUpHandler\n→ rewrite → delegate]
    P4 -->|No| P5
    P5{agentic_rag\n_enabled?} -->|Yes| R5[AgentRAGHandler\nReAct loop]
    P5 -->|No| R6[StandardRAGHandler\nDirect retrieval]
```

---

## Cache Layers

| Level | Key | Populated By | Invalidated After | Purpose |
|-------|-----|-------------|-------------------|---------|
| **L0** | `KEY_RAG_REWRITE` | QueryRewriter | `cache_ttl_rag_query` | Deduplicate follow-up rewrites |
| **L1** | `KEY_RAG_EMBEDDING` | First embed call | `cache_ttl_rag_query` | Reuse expensive embeddings across handlers/tools |
| **L2** | `KEY_RAG_SEARCH_SINGLE/MULTI` | Vector search | `cache_ttl_rag_query` | Reuse pgvector search results |
| **L3** | `KEY_RAG_SUMMARY_SEARCH` | Summary book search | `cache_ttl_rag_query` | Reuse book-selection results |

All caches degrade gracefully: on failure, the pipeline continues uncached with a warning log.

---

## LLM Calls (in execution order)

| # | Call | Handler | Condition | Purpose |
|---|------|---------|-----------|---------|
| 1 | Query rewrite | FollowUpHandler | Follow-up detected | Resolve pronouns → standalone question |
| 2 | Categorize question | StandardRAGHandler | No books found via title/summary/context | Auto-detect book categories to restrict search |
| 3 | Agent ReAct loop (1–4×) | AgentRAGHandler | `agentic_rag_enabled=true` | Tool-calling loop to iteratively retrieve chunks |
| 4 | Answer generation | All handlers (final) | Always | Generate answer from retrieved context |

---

## Key Components

| Component | Role |
|-----------|------|
| **HandlerRegistry** | Evaluates `can_handle()` for each handler in priority order; dispatches to first match |
| **QueryRewriter** | LLM-based standalone question generator; resolves pronouns using conversation history |
| **StandardRAGHandler** | Primary retrieval path: hierarchical book selection → embed → vector search → answer |
| **AgentRAGHandler** | Agentic path: LLM decides which tools to call in a ReAct loop until sufficient chunks collected |
| **AnswerBuilder** | Formats retrieved chunks into LangChain documents; invokes final RAG chain (streaming or batch) |
| **ChunksRepository** | pgvector `similarity_search` against the `chunks` table using cosine distance |
| **BookSummariesRepository** | pgvector `summary_search` against `book_summaries` for coarse book selection |
| **QueryContext** | Mutable dataclass threaded through the whole pipeline; accumulates enriched question, vector, book IDs, scores |
