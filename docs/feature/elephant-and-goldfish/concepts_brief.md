# In-Pipeline Chat Guardrails & Query Short-Circuiting

* **Author:** Omarjan
* **Date:** 2026-11-01

## Overview

Kitabim.AI is a dedicated Uyghur digital library reader and research assistant. Currently, out-of-domain queries (such as programming requests, math homework, and general web assistance) and direct adversarial probes (prompt injection attacks, system architecture and prompt extraction attempts) execute through the entire RAG pipeline. This incurs high latency, consumes up to 12 tool calls in the Retrieval Agent, runs vector and graph searches for non-existent content, and risks Answer Agent jailbreaks.

This feature embeds a two-layer guardrail directly into existing LLM execution points:
1. **Pre-Flight Short-Circuiting (`analyze_query_signals`)**: Extends the existing single-shot structured JSON intent analyzer to classify direct jailbreaks, system architecture probes, and out-of-domain queries. When flagged, the pipeline halts immediately and streams a uniform refusal message in standard Uyghur, bypassing the retrieval agent, vector queries, reranking, and answer generation.
2. **Synthesis Fallback Guardrail (`answer_prompts.py`)**: Hardens Answer Agent system instructions by removing permissive conversational loopholes and adding an explicit fallback refusal if an evasive query bypasses the pre-flight check.

---

## Analysis

### 1. Architectural Strategy & Threat Model
* **Zero Extra Network Roundtrips**: Rather than introducing an external moderation API or an additional pre-flight LLM call (which would add 300–800ms of latency per turn), classification is embedded inside `analyze_query_signals`. This stage already evaluates the question for intent, catalog resolution, and coreference rewriting via Google Gemini. Adding guardrail classification adds no additional network hops.
* **Heuristic Fast-Path Pre-Filter (Strictly Latin/ASCII Script Boilerplate)**:
  * Regex is deliberately **not** used to detect Uyghur-language prompt injections or out-of-domain queries. Uyghur is an agglutinative language where stems undergo extensive suffixation and inflection (e.g., `سىستېما` -> `سىستېمىسىدا`, `كۆرسەت` -> `كۆرسەتمە`). A regex pattern in Uyghur would either cause false-positive rejections on legitimate historical or literary queries (e.g., *«مائارىپ سىستېمىسى»* / educational system) or easily fail against morphological variations.
  * Instead, the heuristic regex pre-filter is strictly confined to universal ASCII/Latin injection boilerplate, special LLM control tokens, and known scripted bot probes (e.g., `ignore previous instructions`, `you are now DAN`, `print system prompt`, `[INST]`, `<|im_start|>`). Because legitimate Uyghur literature queries do not contain these English jailbreak sequences, this filter operates with zero false-positive risk for Uyghur users while eliminating 100% of LLM token costs on automated commodity probes.
* **Prompt Isolation**: In `analyze_query_signals`, the raw question will be wrapped inside `<user_query>` XML tags with strict instruction hierarchy, preventing adversarial prompt inputs from hijacking the JSON analyzer output schema. All Uyghur-language semantic filtering and contextual injection evaluation is performed by Gemini within `analyze_query_signals`.

### 2. Codebase Mechanics & Execution Points
* **`packages/backend-core/app/services/chat/query_signals.py`**:
  * The JSON output schema is extended with:
    ```json
    "guardrail": {
      "is_refusal": boolean,
      "reason": "jailbreak" | "system_probe" | "out_of_domain" | null
    }
    ```
  * Instructions in English direct the model to set `guardrail.is_refusal = true` for direct jailbreaks, system architecture queries, and completely out-of-domain topics, while suppressing tool calls when `is_refusal` is True.
* **`packages/backend-core/app/services/chat/orchestrator.py`**:
  * Upon receiving `guardrail.is_refusal == true`, `ChatOrchestrator` yields `planning` (intent: `refusal`), `answer_start`, a localized refusal chunk, and `answer_end`, then terminates the stream cleanly.
  * Turn history is persisted with `used_book_ids = []` and `eval_status = "skipped"` so background Redis/ARQ jobs (`rag_eval_job`) do not waste worker resources scoring refusals.
* **`packages/backend-core/app/services/chat/answer_prompts.py`**:
  * Existing permissive phrasing (*"If it's a general question or greeting, respond naturally but maintain your persona as a librarian advisor"*) is eliminated.
  * Explicit fallback instructions enforce the uniform refusal if an adversarial or off-topic question slips past Stage 1.5.

### 3. UX & Refusal Delivery
* **Streaming Protocol Parity**: Refusals must not be emitted as SSE `{"error": ...}` events. Emitting errors causes the frontend (`useChat.ts`) to display a red network failure alert. Refusals will stream as standard assistant text chunks, presenting a polite response directly in the message bubble.
* **Refusal Phrasing (Bilingual)**:
  * **Uyghur (`services/backend/locales/ug.json`)**: «كەچۈرۈڭ، مەن پەقەت كىتاب، ئەدەبىيات، تارىخ، لۇغەت ۋە قۇرئانغا مۇناسىۋەتلىك مەزمۇنلارغىلا جاۋاب بېرەلەيمەن. تېمىدىن تاشقىرى ياكى بىخەتەرلىككە خىلاپ تەلەپلەرگە جاۋاب بېرەلمەيمەن.»
  * **English (`services/backend/locales/en.json`)**: "Sorry, I can only answer questions related to books, literature, history, dictionaries, and the Quran. I cannot fulfill out-of-domain or policy-violating requests."

### 4. Semantic Scoping & Over-Refusal Prevention
* **Uyghur Historical and Literary Texts**: Works like *Oyghanghan Zimin* and *Ana Yurt* depict warfare, historical battles, political persecution, and trials. The classification prompt must explicitly instruct the model that analyzing historical conflict, literary characters, and book narratives is completely in-domain and must not be flagged.
* **Domain-Adjacent Topics**: Questions about authors in translation (e.g. Tolstoy, Victor Hugo), Central Asian history, Uyghur orthography/definitions, proverbs, and Quranic verses are in-domain.
* **Permitted Catalog Queries**: Inquiries such as *"Which books do you have by author X?"* or *"What is this book about?"* are recognized catalog intents and are not treated as system probes.
* **Search Misses vs. Out-of-Domain**: If a query is relevant to Uyghur literature/history but no matching passage is found in the database, it must not trigger an out-of-domain rejection; it proceeds to standard RAG retrieval and produces the standard "no match found" response.

---

## Goals vs. Non-Goals

### In-Scope Goals
* **Block Direct Jailbreaks**: Detect and refuse direct adversarial prompt injection, system prompt extraction, and roleplay jailbreaks.
* **Reject System Probes**: Reject inquiries into internal prompts, models, backend infrastructure, and developer instructions.
* **Short-Circuit Out-of-Domain Requests**: Immediately halt execution on non-literary, non-cultural requests (e.g., programming, general mathematics, non-corpus modern politics, financial advice).
* **Zero Extra Latency**: Integrate safety classification into existing LLM calls without adding new network roundtrips.
* **Zero Wasted Worker Load**: Mark short-circuited turns with `eval_status = "skipped"` to prevent queuing background evaluation tasks in Redis/ARQ.
* **Preserve Legitimate Scope**: Allow all catalog queries, reading comprehension questions, historical and literary conflict discussions, and general literature inquiries.

### Out-of-Scope Non-Goals
* **Indirect Prompt Injection Defense**: Defending against malicious payloads embedded inside indexed book OCR text is not addressed in this change (handled separately via document ingestion sanitation).
* **Autonomous Moderation Fine-Tuning**: No fine-tuning of dedicated moderation classifiers or hosting separate self-hosted guardrail microservices (e.g. Llama Guard).
* **Dynamic User Banning / Penalty Engine**: Implementing IP banning, account suspension, or automated abuse reporting thresholds is out-of-scope for this phase.

---

## Alternatives Weighed

1. **Dedicated Pre-Flight Moderation Model (e.g., Llama Guard, NeMo Guardrails)**:
   * *Rejected*: These models add 300–800ms of latency per request, require hosting separate GPU inference infrastructure, and lack robust support for Uyghur Arabic script, leading to high false-positive rates on literary and historical queries.
2. **AnswerAgent-Only System Prompt Hardening**:
   * *Rejected*: Relying solely on instructions in `answer_prompts.py` requires running the entire retrieval pipeline first. An off-topic or jailbreak query would still trigger up to 12 tool calls in the Retrieval Agent and multiple vector/reranking operations, wasting tokens and compute before being refused.
3. **HTTP 400 / SSE Error Event Refusal**:
   * *Rejected*: Sending an error payload triggers the frontend's red system crash alert, degrading user experience. Delivering the refusal as a standard conversational response maintains interface consistency.

---

## Key Decisions & Staging for Next Steps

* **Decision 1**: Restrict the heuristic regex pre-filter strictly to Latin/ASCII injection signatures and control tokens (e.g., `ignore previous instructions`, `[INST]`, `system prompt`). Never use regex for Uyghur semantic filtering; all Uyghur injection and out-of-domain evaluation is handled by Gemini in `analyze_query_signals`.
* **Decision 2**: Extend `analyze_query_signals` with `"guardrail": {"is_refusal": bool, "reason": str}`. If true, `ChatOrchestrator` immediately streams the localized refusal and ends the turn.
* **Decision 3**: Harden `answer_prompts.py` by removing the general chit-chat clause and adding an explicit fallback instruction.
* **Decision 4**: Bypass ARQ evaluation queueing on refusals (`eval_status = "skipped"`).
* **Next Steps**:
  1. Review key trade-offs with stakeholders.
  2. Transition to formal drafting via `/egm-draft` or proceed directly to implementation.

