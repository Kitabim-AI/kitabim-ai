# Question Answering Pipeline Diagram (Deterministic Router & Google ADK)

Visual representation of the RAG question answering pipeline, supporting both the **Deterministic Python Router** and the **Google ADK Agentic Loop** (fallback).

---

## Full Pipeline

```mermaid
flowchart TD
    %% Entry
    Q(["User Question<br/>+ Chat History<br/>+ Context"]) --> BUILD

    %% Context build
    subgraph ContextBuild ["_build_context — rag_service.py"]
        BUILD["Resolve character, models<br/>read system_configs"] --> CTX[QueryContext]
    end

    CTX --> ROUTE{use_deterministic_router?}

    ROUTE -- Yes --> H_DET["DeterministicRAGHandler<br/>(Deterministic Router)"]
    ROUTE -- No --> H_AG["AgentRAGHandler<br/>(Google ADK Fallback)"]

    %% Deterministic Router Flow
    subgraph DetRouter ["Deterministic RAG Flow"]
        H_DET --> S1_DB["DB Metadata Check<br/>(Fuzzy Title & Author)"]
        S1_DB --> S1_LLM["[LLM] Unified Query Analyzer<br/>(Extract intent, signals, & rewrite)<br/>emits: planning / rewrite_query"]
        S1_LLM --> S4["Stage 2: Execution Router<br/>(Run path A-H directly)"]
        S4 --> T_DET["Execute Path Tool<br/>emits: tool_call<br/>tool_result"]
        T_DET -->|Return observations| S4
        S4 --> DET_MERGE["Universal Fallback Check<br/>(Widen if < 4 chunks)"]
    end

    %% Agentic RAG — Google ADK Execution Flow
    subgraph AgentRAG ["AgentRAGHandler — Google ADK"]
        H_AG --> INTENT["Intent Detection<br/>_detect_intent<br/>emits: planning"]
        INTENT --> DECOMP["[LLM] Query Decomposition<br/>_llm_split<br/>emits: decompose"]
        DECOMP --> CTX_INJ["Context Injection<br/>_build_human_message<br/>Inject [Context] block:<br/>current book_id, context book IDs,<br/>category filter"]
        CTX_INJ --> ADK["[LLM] ADK Agent Execution<br/>InMemoryRunner.run_async<br/>emits: agent_thinking"]

        ADK -->|Call Tools| TOOL["Execute Tool<br/>(11 tools available)<br/>emits: tool_call<br/>tool_result"]
        TOOL -->|Return observation<br/>data| ADK

        ADK -->|Finish Loop / Max Steps| DEDUP["Deduplicate Observations<br/>by book_id and page"]
    end

    DET_MERGE --> GRADE
    DEDUP --> GRADE

    subgraph PostProcess ["Post-processing & Generation"]
        GRADE["Context Grading<br/>_grade_context<br/>filter low-relevance chunks<br/>emits: grading"]
        GRADE --> SYNTHESIS["[LLM] Answer Synthesis<br/>generate_answer_stream<br/>emits: answer_start<br/>chunk × N<br/>answer_end"]
        SYNTHESIS --> END_AG(["END<br/>write final_answer"])
    end

    END_AG --> ANS(["Answer delivered to user"])

    classDef handler fill:#e9edc9,stroke:#606c38,stroke-width:2px
    classDef tool fill:#dcfce7,stroke:#16a34a,stroke-width:1px
    classDef process fill:#d4f1f4,stroke:#189ab4,stroke-width:1px
    classDef llm fill:#fef08a,stroke:#ca8a04,stroke-width:2px

    class H_AG,H_DET handler
    class TOOL,T_DET tool
    class INTENT,CTX_INJ,DEDUP,GRADE,S1_DB,S4,DET_MERGE process
    class DECOMP,ADK,SYNTHESIS,S1_LLM llm
```

---

## Handler Routing Reference

Handler selection is dynamically governed by the `use_deterministic_router` config:

```mermaid
flowchart LR
    Q([Question]) --> REG["HandlerRegistry"]
    REG --> CAN_DET{"can_handle?<br/>(use_deterministic_router == true)"}
    CAN_DET -- Yes --> DET["DeterministicRAGHandler<br/>Deterministic path selection"]
    CAN_DET -- No --> ADK["AgentRAGHandler<br/>ADK ReAct reasoning loop"]
    DET --> ANS([Answer])
    ADK --> ANS([Answer])
```

---

## Agent Prompt Routing Decision Tree

This diagram illustrates the agent's internal decision tree for tool selection, governed entirely by the `AGENT_SYSTEM_PROMPT` in [prompts.py](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/rag/agent/prompts.py).

```mermaid
flowchart TD
    %% Entry & Step 1: Co-reference
    Start([User Question Received]) --> Step1{"Step 1: Uyghur pronouns or 'چۇ' particle + history?"}
    Step1 -- "Yes" --> Rewrite["Call Tool: rewrite_query (Resolve co-references)"]
    Rewrite --> CheckTitle{"Rewritten query names book title?"}
    CheckTitle -- "Yes" --> FindTitle["Call Tool: find_books_by_title (Do NOT reuse previous book IDs)"]
    FindTitle --> Step2
    CheckTitle -- "No" --> Step2
    Step1 -- "No" --> Step2

    %% Step 2: Catalog & Metadata
    Step2{"Step 2: Catalog or Metadata query?"}
    Step2 -- "Yes: 'Who wrote title?'" --> ToolAuthor["Call Tool: get_book_author"] --> Stop
    Step2 -- "Yes: 'What did author write?'" --> ToolBooksAuthor["Call Tool: get_books_by_author"] --> Stop
    Step2 -- "Yes: Library browsing" --> ToolCatalog["Call Tool: search_catalog"] --> Stop
    Step2 -- "No" --> Step3

    %% Step 3: Current Page Reading
    Step3{"Step 3: Question about currently read page?"}
    Step3 -- "Yes" --> ToolCurrentPage["Call Tool: get_current_page (Stop; do NOT call search_chunks)"] --> Stop
    Step3 -- "No" --> Step4

    %% Step 4: Quran Queries
    Step4{"Step 4: Quran query? (Surah, Ayah, Translation)"}
    Step4 -- "Yes" --> ToolQuran["Call Tool: search_quran (Stop; do NOT call book/dict tools)"] --> Stop
    Step4 -- "No" --> Step5

    %% Step 5: Dictionary & Language
    Step5{"Step 5: Uyghur dictionary / language query?"}
    Step5 -- "Yes" --> DictRouter{"Dictionary Type"}
    DictRouter -- "Word definition" --> ToolLookupWord["Call Tool: lookup_uyghur_word"]
    DictRouter -- "Historical term/person" --> ToolLookupHist["Call Tool: lookup_history_term (Fallback: search_language_sources)"]
    DictRouter -- "Eng-to-Uyg Translation" --> ToolTranslate["Call Tool: translate_english_to_uyghur"]
    DictRouter -- "Spelling Check" --> ToolSpelling["Call Tool: check_word_spelling"]
    DictRouter -- "Uyghur Name Lookup" --> ToolLookupName["Call Tool: lookup_uyghur_name"]
    DictRouter -- "Proverbs/Sayings" --> ToolProverbs["Call Tool: lookup_proverbs"]
    DictRouter -- "Unclear Source" --> ToolSearchLang["Call Tool: search_language_sources"]
    
    ToolLookupWord --> DictStop{"User only asked for definition/translation/etc?"}
    ToolLookupHist --> DictStop
    ToolTranslate --> DictStop
    ToolSpelling --> DictStop
    ToolLookupName --> DictStop
    ToolProverbs --> DictStop
    ToolSearchLang --> DictStop
    
    DictStop -- "Yes: Only definition" --> Stop
    DictStop -- "No: Also ask about books/library usage" --> Step6
    Step5 -- "No" --> Step6

    %% Step 6: Content Retrieval
    subgraph Step6Content ["Step 6: Content Retrieval & Passage Search"]
        Step6{"Step 6 Path Router"}
        
        %% Step 6 Rules & Modifiers
        Step6 --> Modifiers["Apply Modifiers:<br/>1. Relationship Query + Graph Available -> query_knowledge_graph first<br/>2. Character/Entity Identity ('Who is X?') -> Use get_book_summary paths"]
        
        Modifiers --> PathRouter{"Query Context / Named Entities"}
        
        %% Path a: Plot/Theme of Specific Book
        PathRouter -- "a. Plot/Theme of named book" --> PathA["find_books_by_title<br/>↓<br/>get_book_summary (Do NOT call search_chunks)"] --> Step7
        
        %% Path b: Details of Named Book
        PathRouter -- "b. Details/Passages of named book" --> PathB["find_books_by_title<br/>↓<br/>search_chunks (with book IDs)"] --> CheckChunks
        
        %% Path c: Named Author
        PathRouter -- "c. Named Author" --> PathC["get_books_by_author<br/>↓<br/>search_chunks (with book IDs)"] --> CheckChunks
        
        %% Path d: Current Book Context (No explicit book name)
        PathRouter -- "d. Has current book ID in context" --> PathD{"Is sister volume query?"}
        PathD -- "Yes" --> PathDSis["get_sister_volumes<br/>↓<br/>search_chunks (sister volume ID)"] --> CheckChunks
        PathD -- "No" --> PathDCur["search_chunks (current book ID)"] --> CheckChunks
        
        %% Path e: Context Book IDs (Character identity query)
        PathRouter -- "e. Has previous book IDs + Character query" --> PathE["search_books_by_summary (verify topic)<br/>↓<br/>get_book_summary (max 5 IDs)"] --> Step7
        
        %% Path f: Context Book IDs (Non-character detail query)
        PathRouter -- "f. Has previous book IDs + Detail query" --> PathF{"Is sister volume query?"}
        PathF -- "Yes" --> PathFSis["get_sister_volumes<br/>↓<br/>search_chunks (sister volume ID)"] --> CheckChunks
        PathF -- "No" --> PathFCur["search_chunks (prev book IDs)"] --> CheckChunks
        
        %% Path g: General fallback
        PathRouter -- "g. All other cases / general topic" --> PathG["search_books_by_summary (discover book IDs)<br/>↓<br/>search_chunks (or get_book_summary if character query)"]
        PathG --> CheckChunks
        
        %% Chunks threshold check & broadening (Path h)
        CheckChunks{"Step 6h: Chunks returned < 4?"}
        CheckChunks -- "Yes" --> RetryRephrased["Retry with rephrased query in same scope"]
        RetryRephrased --> CheckChunks2{"Chunks still < 4?"}
        CheckChunks2 -- "Yes" --> Broaden["search_chunks (empty book_ids list = global library)"] --> Step7
        CheckChunks2 -- "No" --> Step7
        CheckChunks -- "No" --> Step7
    end

    %% Step 7/8/Limits: Stopping and Loops
    Step7{"Step 7: Sufficient context (6-12 chunks) or Hard Limit reached?"}
    Step7 -- "No" --> Step8{"Step 8: Has pending Sub-questions?"}
    Step8 -- "Yes" --> Step8Loop["Get next sub-question (Always find_books/summaries fresh; do NOT reuse old IDs)"] --> Step1
    Step8 -- "No" --> Stop
    Step7 -- "Yes" --> Stop

    Stop([Stop: Respond with NO tool calls to signal completion])

    classDef tool fill:#dcfce7,stroke:#16a34a,stroke-width:2px
    classDef decision fill:#fef9c3,stroke:#854d0e,stroke-width:1px
    classDef stop fill:#fee2e2,stroke:#dc2626,stroke-width:2px
    classDef llm fill:#fef08a,stroke:#ca8a04,stroke-width:2px

    class Rewrite,FindTitle,ToolAuthor,ToolBooksAuthor,ToolCatalog,ToolCurrentPage,ToolQuran,ToolLookupWord,ToolLookupHist,ToolTranslate,ToolSpelling,ToolLookupName,ToolProverbs,ToolSearchLang,PathA,PathB,PathC,PathDSis,PathDCur,PathE,PathFSis,PathFCur,PathG,RetryRephrased,Broaden tool
    class Step1,CheckTitle,Step2,Step3,Step4,Step5,DictRouter,DictStop,PathRouter,PathD,PathF,CheckChunks,CheckChunks2,Step7,Step8 decision
    class Stop stop
```

### Key Prompt Rules

* **Co-reference Resolution (Step 1)**:
  * **When to Call**: Pronoun or topic-shift clitic present, AND `[Context]` explicitly shows `Chat history: Available`.
  * **When NOT to Call**: No chat history present, or if the pronoun's antecedent is already named in the same turn (e.g., *"Yunus Khan is who? How many children did he have?"*).
  * **Post-Rewrite**: If the rewritten question resolves to a book title, the agent MUST immediately invoke `find_books_by_title` rather than reusing stale context IDs.
* **Separation of Sources (Step 4 & 5)**: 
  * Quran queries (Step 4) are strictly routed to `search_quran` and terminate immediately.
  * Dictionary definitions, translations, name checks, and proverb lookups (Step 5) run respective dictionary tools and stop immediately unless a book-level usage is explicitly queried.
* **Knowledge Graph Modifier (Step 6)**: Queries asking about relationships or lineages must call `query_knowledge_graph` to retrieve entity relationship networks before/alongside `search_chunks`.
* **Character Identity Optimization (Step 6e/g)**: Biographical queries (*"Who is X?"*) utilize `get_book_summary` instead of raw text chunks `search_chunks`, preventing irrelevant context.
* **Broadening (Step 6h)**: Global library search (`book_ids=[]`) is strictly forbidden as a first action and serves only as a fallback when scoped retrieval yields `< 4` passages.
* **Hard Limits**: The agent is bounded by a maximum of 6 tool calls per turn (increased to 10 for turns containing multiple `[Sub-questions]`).

---

## Agent Tools Reference

| Tool | Type | Wraps | When agent calls it |
|------|------|-------|---------------------|
| `rewrite_query` | Utility | `QueryRewriter` | Question has pronouns or follow-up markers ("چۇ" clitic) and chat history exists. |
| `find_books_by_title` | Content | `BooksRepository` title match | Question explicitly names a book title; returns book IDs, title, author, and volume metadata. |
| `search_books_by_summary` | Content | `BookSummariesRepository` | Finding which books cover a topic; also used with `context_book_ids` to verify a "who is X" question. |
| `search_chunks` | Content | pgvector similarity search | Retrieving passages; uses L1+L2 cache; called directly with `[Context]` book_id when available. |
| `get_book_author` | Metadata | `BooksRepository` | Author lookup for "who wrote X?" questions. |
| `get_books_by_author` | Metadata | `BooksRepository` | Book list for "what did Y write?" questions. |
| `get_book_summary` | Content | `BookSummariesRepository` | Plot, themes, or main characters of specific books; or identifying characters/persons. |
| `get_current_page` | Content | `PagesRepository.find_one` | Raw text of the page the user is currently reading (in-reader mode). |
| `get_sister_volumes` | Content | `BooksRepository` | All volumes of the same series as a given book_id. |
| `search_catalog` | Metadata | `CatalogHandler` | Library browsing and general listing queries. |
| `query_knowledge_graph` | Content | `GraphRepository` | Queries Neo4j to retrieve connections between entities. |

---

## Cache Layers

| Level | Key | Populated By | Purpose |
|-------|-----|-------------|---------|
| **L0** | `KEY_RAG_REWRITE` | `rewrite_query` tool | Deduplicate follow-up pronoun rewrites |
| **L1** | `KEY_RAG_EMBEDDING` | First embed call per query | Reuse query embeddings across multiple tools |
| **L2** | `KEY_RAG_SEARCH_SINGLE/MULTI` | `search_chunks` tool | Cache pgvector similarity search results |
| **L3** | `KEY_RAG_SUMMARY_SEARCH` | `search_books_by_summary` tool | Cache summary search results for book selection |

---

## LLM Calls (in execution order)

| # | Call | Triggered By | Condition | Purpose |
|---|------|-------------|-----------|---------|
| 1 | Query decomposition | Pre-processing (`_llm_split`) | Only when input has > 1 `?`/`؟` | Split multi-question inputs into sub-questions. |
| 2 | Agent ReAct loop (1–4×) | ADK Agent run | Always | Reasoning loop — choose and invoke retrieval tools. |
| 3 | Entity Extraction | `query_knowledge_graph` tool | When KG tool runs | Extract query entities for Cypher generation. |
| 4 | Answer generation | Post-processing (`generate_answer_stream`) | Always | Stream final answer from accumulated context. |

---

## Key Components

| Component | Role |
|-----------|------|
| **HandlerRegistry** | Registry for the active RAG query handler (`AgentRAGHandler`). |
| **AgentRAGHandler** | Main execution driver — performs pre-agent decomposition, invokes ADK runner, collects observations, executes grading, and runs synthesis. |
| **Google ADK Agent** | Stateless agent compiled with tools and system prompts. |
| **InMemoryRunner** | Stateless runner executing the agent ReAct loop. |
| **QueryRewriter** | Resolves pronouns using conversation history (L0 cached). |
| **_grade_context** | Post-processing method applying relative grading thresholds per search tool call to keep diverse topic matches, deduplicating, and capping at `AGENT_MAX_CONTEXT_CHUNKS` (25 chunks). |
| **retrieval.py** | Shared database retrieval primitives (`embed_query`, `vector_search`, `find_books_by_title_in_question`). |
| **agent/config.py** | Centralized loop constants (`AGENT_MAX_STEPS`, `AGENT_ENOUGH_CHUNKS`, `AGENT_MAX_CONTEXT_CHUNKS`, etc.). |
| **ChunksRepository** | pgvector `similarity_search` against PostgreSQL `chunks` table. |
| **BookSummariesRepository** | pgvector `summary_search` against `book_summaries` for book discovery. |
