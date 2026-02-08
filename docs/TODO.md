# Architecture Improvement TODOs

## Phase 1 — Stabilize & Make Observable
1) Add request/job correlation IDs and structured JSON logging in backend ✅
2) Add health/readiness endpoints for backend API ✅
3) Add DB indexes for `contentHash`, `status`, `uploadDate`, `tags`, `categories` ✅
4) Add error model for OCR/embedding/chat with persisted error summaries ✅

## Phase 2 — Background Processing & Reliability
5) Introduce a job queue + worker (Celery/RQ/Arq) for OCR/embedding/RAG ✅
6) Refactor OCR/embedding into idempotent tasks with retries ✅
7) Add task status tracking and retries in DB ✅

## Phase 3 — Storage & Security
8) Add storage abstraction layer (local FS vs S3/MinIO)
9) Stop exposing Gemini API key to frontend; proxy all AI calls via backend ✅
10) Add secrets handling best practices for dev/prod configs

## Phase 4 — LangChain Modernization
11) Refactor LLM pipelines to LCEL (Runnable chains) ✅
12) Add structured output parsing for metadata extraction ✅
13) Add caching for repeated LLM calls ✅
14) Add tracing (LangSmith or OTel callbacks) ✅
15) Add RAG evaluation hooks + metrics ✅
16) Add circuit breaker for LLM API calls ✅

## Phase 5 — Contract & Client Hardening
17) Generate TS API types from OpenAPI
18) Add API client schema validation (Zod) + smoke tests
