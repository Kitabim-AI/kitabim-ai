# Ragas Framework Integration Plan

**Last Updated:** 2026-05-20  
**Status:** 🚧 Draft  

This document outlines the design and integration plan for incorporating the **Ragas (Retrieval Augmented Generation Assessment)** framework into Kitabim.AI. This will provide automated, semantic evaluation of both the retrieval and generation phases of our Agentic RAG pipeline.

---

## 🎯 Goals

| Goal | Mechanism |
|------|-----------|
| **Quantifiable Answer Quality** | Grade generation output for faithfulness (groundedness) and relevance using LLM-as-a-judge. |
| **Verify Retrieval Performance** | Measure context precision and recall to validate our LangGraph agent's tool-calling logic. |
| **Regression Testing** | Enable automated test suites (offline) to benchmark RAG performance before merging updates. |
| **Online Curation Analytics** | Asynchronously score a sample of real-user queries and display quality metrics on the admin panel. |

---

## 📊 Ragas Metrics Mapping

Ragas provides specialized metrics that map directly to different stages of our RAG architecture:

```
                  ┌──────────────────────┐
                  │   User Question      │
                  └──────────┬───────────┘
                             │
                             ▼             Context Recall / Context Precision
                      [ Retrieval ]  ◄───  (Evaluates LangGraph Agent tools:
                             │             search_chunks, search_books_by_summary)
                             ▼
                    [ Aggregated Context ]
                             │             Faithfulness / Groundedness
                             ▼  ◄────────  (Evaluates if the answer is fully
                       [ Generator ]       derived from the retrieved text)
                             │
                             ▼             Answer Relevance
                    [ Streaming Answer ] ◄─ (Evaluates if the response actually
                             │             answers the user's intent)
                             ▼
```

1. **Faithfulness (0 - 1):** Measures how factual the answer is relative to the retrieved context. This is crucial for catching hallucinations in the Gemini generation step.
2. **Answer Relevance (0 - 1):** Evaluates if the generated answer directly addresses the user's question, penalizing incomplete, repetitive, or vague answers.
3. **Context Recall (0 - 1):** Compares the retrieved context to a ground-truth answer to verify if the LangGraph agent gathered all required pages to answer the question.
4. **Context Precision (0 - 1):** Checks if the retrieved chunks are highly relevant, helping us optimize search caps (currently capped at 15 chunks) and similarity thresholds.

---

## 🏗️ Proposed Architecture

The integration will be structured in **three distinct phases** to minimize risk and manage API usage costs.

```
                    [ Phase 1: Offline CLI Benchmarking ]
                                     │
                                     ▼
                    [ Phase 2: DB & Model Migrations ]
                                     │
                                     ▼
               [ Phase 3: Online Async ARQ Worker Scoring ]
                                     │
                                     ▼
                  [ Phase 4: Admin UI Dashboard Stats ]
```

### Phase 1: Offline Evaluation (Golden Dataset & CLI)
This phase introduces a test runner that executes evaluation runs against a static benchmark of questions.

* **Golden Dataset:** A JSON file `tests/data/rag_golden_dataset.json` containing:
  ```json
  [
    {
      "question": "ئىسكەندەرنامە رومانىنىڭ ئاساسلىق تېمىسى نېمە؟",
      "ground_truth": "روماندا ئىسكەندەر زۇلقەرنەيننىڭ ھاياتى ۋە تارىخىي ۋەقەلەر ئاساسلىق تېما قىلىنغان...",
      "reference_book_id": "iskandarname_vol1"
    }
  ]
  ```
* **CLI Test Runner:** A Python script [scripts/run_ragas_eval.py](file:///Users/Omarjan/Projects/kitabim-ai/scripts/run_ragas_eval.py) that:
  1. Bootstraps the FastAPI application context.
  2. Runs each golden query through `RAGService.answer_question()`.
  3. Collects the question, retrieved chunks, and generated answer.
  4. Calls `ragas.evaluate()` using the LangChain-Gemini judge config (`langchain-google-genai`).
  5. Outputs the average score reports and logs them to `./data/eval_runs/`.

### Phase 2: Database and Model Migrations
We will expand the existing `RAGEvaluation` model in [models.py](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/db/models.py) to store Ragas metrics.

#### Database Columns
Add the following columns to `rag_evaluations`:
* `faithfulness_score`: `Float` (nullable)
* `answer_relevance_score`: `Float` (nullable)
* `context_precision_score`: `Float` (nullable)
* `context_recall_score`: `Float` (nullable)
* `eval_status`: `String(20)` (default `"pending"` for online async evaluation)

#### Alembic Migration
Create a migration script `packages/backend-core/migrations/042_add_ragas_columns.sql`:
```sql
ALTER TABLE rag_evaluations
ADD COLUMN faithfulness_score FLOAT NULL,
ADD COLUMN answer_relevance_score FLOAT NULL,
ADD COLUMN context_precision_score FLOAT NULL,
ADD COLUMN context_recall_score FLOAT NULL,
ADD COLUMN eval_status VARCHAR(20) DEFAULT 'pending' NOT NULL;
```

### Phase 3: Online Asynchronous Evaluation (ARQ Worker)
To avoid blocking the user response, online grading will happen asynchronously:

```
User Query ──► RAGService ──► Stream Answer to User
                 │
                 ├─► If rag_eval_enabled == true & should_sample:
                 ▼
             Write RAGEvaluation row (status: 'pending')
                 │
                 ▼
             Enqueue ARQ Job: evaluate_rag_query(eval_id)
                 │
                 ▼
             ARQ Worker executes Ragas evaluation with Gemini judge
                 │
                 ▼
             Update DB Row: Set scores + status: 'completed'
```

1. **Sampling Strategy:** System configuration `rag_eval_sampling_rate` (e.g. `0.05` for 5% of queries) determines whether a query is graded. Additionally, any query that receives negative user feedback will be automatically enqueued.
2. **ARQ Job:** Implement `evaluate_rag_query(ctx, eval_id)` in [services/worker/](file:///Users/Omarjan/Projects/kitabim-ai/services/worker/):
   * Fetch the `RAGEvaluation` record.
   * Assemble the payload into a Ragas `Dataset`.
   * Invoke `ragas` using the system configured judge model (`gemini_chat_model` or `gemini_agent_loop_model`).
   * Write scores back to PostgreSQL and mark `eval_status = 'completed'`.

### Phase 4: Admin Dashboard Updates
The admin panel in [StatsPanel.tsx](file:///Users/Omarjan/Projects/kitabim-ai/apps/frontend/src/components/admin/StatsPanel.tsx) will be updated to display:
* Average Faithfulness and Answer Relevance over time (daily/weekly charts).
* Detailed query logs filtering for queries where `faithfulness_score < 0.70` (potential hallucinations).
* Distribution of tool calling patterns vs. semantic scores.

---

## 🌐 Uyghur Language Support and LLM Tuning

Ragas default prompts are designed for English evaluation. Since Kitabim.AI operates primarily in **Uyghur (Perso-Arabic script)**, we must configure Ragas to prevent false-negative scores:

1. **Judge Instruction Customization:**
   We will override the default evaluation prompt templates of Ragas with versions instructing the judge model (Gemini) that the inputs are in Uyghur, and that morphological variations (agglutinative suffixes) should not be treated as incorrect details.
2. **Context Formatting:**
   Ensure the retrieved chunks keep their Uyghur right-to-left layout and are parsed cleanly without markup noise.

---

## ⚠️ Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| **Gemini API Cost Inflation** | Restrict online evaluations to a configurable sampling rate (e.g. 5%) and user-flagged queries only. Use the `gemini-3-flash-preview` model for evaluations (which supports Uyghur). |
| **Increased Worker Queue Depth** | Run Ragas jobs on a separate, low-priority worker queue so they don't block core tasks like OCR, chunking, or embedding. |
| **LLM Judge Hallucination** | Use a golden dataset of human-annotated evaluations to verify the accuracy of the Ragas judge before deploying Phase 3. |
