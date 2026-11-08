# PostgreSQL Container Initialization

## Overview
PostgreSQL database initialization script providing essential database extensions required by Kitabim for vector embeddings and unique identifier generation.

## Interface
- `[init.sql:CREATE EXTENSION IF NOT EXISTS vector]`: Registers `vector` (pgvector) extension for vector embeddings storage and cosine similarity search.
- `[init.sql:CREATE EXTENSION IF NOT EXISTS "uuid-ossp"]`: Registers `uuid-ossp` extension for UUID generation functions.

## Invariants
- `[init.sql]`: Runs automatically on the initial creation of the PostgreSQL container database instance.

## Side Effects
- `[init.sql]`: Modifies the PostgreSQL database catalog to install system extensions.

## Verification
- Run: `docker compose ps`
