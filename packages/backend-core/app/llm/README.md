# LLM & Embeddings Integration (`app/llm`)

## Overview
Wraps Google Gemini client operations, multimodal generation, circuit breakers, LangChain chains, pgvector embeddings, and token cost tracking across the application.

## Interface
- `[models.py:generate_text]` — `generate_text(...) -> str`: Invokes Gemini text generation with circuit breaker and retry logic.
- `[models.py:generate_text_with_image]` — `generate_text_with_image(...) -> str`: Multimodal generation for image OCR and document inspection.
- `[models.py:is_llm_available]` — `is_llm_available() -> bool`: Inspects circuit breaker state for LLM availability.
- `[models.py:reset_circuit_breakers]` / `[models.py:get_circuit_breaker_status]` — Circuit breaker administrative controls and telemetry.
- `[models.py:ProtectedLLM]` — LangChain-compatible LLM wrapper guarded by circuit breaker checks.
- `[models.py:GeminiEmbeddings]` — Embeddings client implementing document and query embedding generation.
- `[models.py:DegenerateOcrOutputError]` — Exception raised when OCR generation produces repetitive or degenerate token loops.
- `[models.py:is_transient_error]` — Identifies retryable HTTP/API errors (429, 503, ResourceExhausted).
- `[chains.py:TextChain]` — LangChain text generation pipeline wrapper.
- `[chains.py:StructuredChain]` — Pydantic-grounded structured JSON output extraction chain.
- `[chains.py:build_text_chain]` / `[chains.py:build_structured_chain]` — Factory constructors for text and structured generation chains.
- `[cost_tracker.py:CostTracker]` — Context-managed token tracker recording cumulative prompt/completion tokens and computing total cost.
- `[pricing.py:estimate_cost_usd]` — `estimate_cost_usd(model_name: str, input_tokens: int, output_tokens: int) -> float`: Calculates USD API cost from configured model pricing rates.
- `[pricing.py:get_model_pricing_from_repo]` — Retrieves active model pricing mappings from database configuration.

## Invariants
- `[models.py:DegenerateOcrOutputError]` — Halts and flags OCR processing when text repeats identical phrases or exhibits degenerative hallucination loops.
- `[models.py:is_transient_error]` — Filters exceptions to ensure non-retryable client errors (400, 401, 404) fail fast without triggering circuit breaker penalties.
- `[cost_tracker.py:CostTracker]` — Cost calculations default to standard fallback rates if database pricing is unavailable.

## Side Effects
- Performs outbound network HTTPS requests to Google Gemini Generative AI endpoints.
- Mutates circuit breaker state counters and logs request metrics and costs.

## Verification
- Run: `pytest packages/backend-core/tests`
