# Services

## Overview
Core runtime services powering the Kitabim.AI platform, partitioned into the synchronous FastAPI HTTP API service and the asynchronous Redis/ARQ pipeline worker.

## Subdirectories & Boundaries
- Backend: [./backend/README.md](./backend/README.md) - FastAPI HTTP service providing REST API endpoints, JWT authentication, RBAC authorization, AI proxy routes, and dictionary services.
- Worker: [./worker/README.md](./worker/README.md) - Asynchronous background worker service running ARQ task queues over Redis for document OCR, text chunking, vector embedding, spell checking, and knowledge graph construction.
