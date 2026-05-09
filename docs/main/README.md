# Kitabim.ai Documentation

**Last Updated:** 2026-05-09

Welcome to the Kitabim.ai documentation. This directory contains comprehensive technical documentation for the platform.

---

## 📚 Documentation Index

### **🏗️ Architecture & Design**

| Document | Description | Status |
|----------|-------------|--------|
| [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) | High-level system architecture and design decisions | ✅ Current |
| [WORKER_DESIGN.md](WORKER_DESIGN.md) | Event-driven pipeline architecture and worker components | ✅ Current |
| [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | Monorepo structure and codebase organization | ✅ Current |
| [AGENTIC_RAG_DESIGN.md](AGENTIC_RAG_DESIGN.md) | Agentic RAG design — 7 tools, context injection, follow-up detection | ✅ Current |
| [QUESTION_ANSWERING_DIAGRAM_V2.md](QUESTION_ANSWERING_DIAGRAM_V2.md) | Visual pipeline diagram — current agentic RAG state | ✅ Current |
| [QUESTION_ANSWERING_DIAGRAM.md](QUESTION_ANSWERING_DIAGRAM.md) | Visual pipeline diagram — pre-agentic (archived) | ⚠️ Archived |
| [book_processing_diagram.md](book_processing_diagram.md) | Visual diagrams of the book processing pipeline | ✅ Current |
| [code-review-api-2026-03-29.md](code-review-api-2026-03-29.md) | API code review snapshot — blocking issues still open | ⚠️ Open issues |

### **⚡ Performance & Optimization**

| Document | Description | Status |
|----------|-------------|--------|
| Pipeline optimizations (2x speedup, applied 2026-03-14) | MAX_PARALLEL_PAGES=6, EMBED_BATCH_SIZE=50 — see `.env.template` | ✅ Applied (env vars only) |
| Redis caching strategy | Redis caching for books, configs, proverbs — see `.env.template` CACHE_TTL_* vars | ✅ Complete |

### **📊 Operations & Monitoring**

| Document | Description | Status |
|----------|-------------|--------|
| [VM_MONITORING.md](VM_MONITORING.md) | Production VM monitoring guide and commands | ✅ Current |

### **🤖 AI & RAG**

| Document | Description | Status |
|----------|-------------|--------|
| [AGENTIC_RAG_DESIGN.md](AGENTIC_RAG_DESIGN.md) | Agentic ReAct loop, 7 tools, context injection, follow-up detection | ✅ Current |
| [QUESTION_ANSWERING_DIAGRAM_V2.md](QUESTION_ANSWERING_DIAGRAM_V2.md) | Full pipeline visual diagram — current state | ✅ Current |

### **🔧 Features & Implementation**

| Document | Description | Status |
|----------|-------------|--------|
| Hierarchical RAG with book summaries | `book_summaries` table + `summary_scanner` + `summary_job` | ✅ Implemented |
| [UI_CSS_STANDARD.md](UI_CSS_STANDARD.md) | Frontend CSS conventions and Tailwind standards | ✅ Current |

### **📋 Requirements & Specifications**

| Document | Description | Status |
|----------|-------------|--------|
| [REQUIREMENTS.md](REQUIREMENTS.md) | Product requirements and feature specifications | ✅ Current |
| [openapi.json](openapi.json) | OpenAPI specification for REST API | ✅ Generated |

---

## 🎯 Quick Start Guides

### **For Developers**

1. **Understanding the System:**
   - Start with [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) for architecture overview
   - Read [WORKER_DESIGN.md](WORKER_DESIGN.md) to understand the pipeline
   - Check [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for codebase layout

2. **Making Changes:**
   - Performance: See `.env.template` for pipeline tuning vars (MAX_PARALLEL_PAGES, EMBED_BATCH_SIZE, CACHE_TTL_*)
   - UI: Follow [UI_CSS_STANDARD.md](UI_CSS_STANDARD.md) conventions

### **For Operations**

1. **Monitoring Production:**
   - Use [VM_MONITORING.md](VM_MONITORING.md) for monitoring commands
   - Run `/scripts/monitor.sh` for quick health checks

2. **Troubleshooting & Deployment:**
   - Local Rebuild: `./deploy/local/rebuild-and-restart.sh [all|backend|worker|frontend]`
   - Production Deploy: `./deploy/gcp/scripts/deploy.sh [tag]`
   - Check worker logs: `docker logs -f worker`
   - Monitor queue depth: Redis LLEN commands (see VM_MONITORING.md)
   - Review pipeline state in admin dashboard

---

## 🗂️ Document Categories

### Architecture Documents
- **Purpose:** Explain system design and architectural decisions
- **Audience:** Senior developers, architects, new team members
- **Update Frequency:** When major architectural changes occur

### Operations Documents
- **Purpose:** Provide operational procedures and monitoring guides
- **Audience:** DevOps, SREs, on-call engineers
- **Update Frequency:** When deployment or infrastructure changes

### Feature Documents
- **Purpose:** Document specific features and their implementation
- **Audience:** Developers working on or using the feature
- **Update Frequency:** When feature behavior changes

---

## 📝 Documentation Standards

### File Naming
- `UPPERCASE_WITH_UNDERSCORES.md` for major architecture/system docs
- `lowercase-with-dashes.md` for feature-specific docs
- Prefix with number for migrations: `015_description.md`

### Structure
All docs should include:
- **Date** or **Last Updated** timestamp
- **Status** indicator (✅ Current, ⚠️ Outdated, 🚧 Draft)
- **Table of Contents** for docs >500 lines
- **Examples** for technical guides

### Maintenance
- Review quarterly for accuracy
- Mark outdated docs with ⚠️ and date
- Remove obsolete docs (move to `/docs/archive` if historical value)
- Update diagrams when architecture changes

---

## 🏗️ Current System State (April 2026)

### Technology Stack
- **Database:** PostgreSQL 17 with pgvector
- **Cache/Queue:** Redis 7
- **Backend:** Python 3.13 + FastAPI + SQLAlchemy
- **Frontend:** React 19 + Vite 6 + TypeScript 5.8
- **Worker:** ARQ (async Redis queue)
- **AI:** Google Gemini 2.0 Flash (OCR, embeddings, chat)
- **Storage:** Google Cloud Storage
- **Deployment:** Docker Compose on GCP VM (e2-standard-2)

### Key Metrics (March 2026)
- **Books in Library:** ~150 books
- **Pipeline Speed:** ~15 minutes for 300-page book
- **Cache Hit Rate:** ~75%
- **Uptime:** 99.9%

### Recent Major Changes
- ✅ **2026-05-09:** Agentic RAG fully promoted — always-on, 7 tools, context injection, "چۇ" follow-up detection, `StandardRAGHandler` removed
- ✅ **2026-03-14:** Applied pipeline optimizations (2x speedup)
- ✅ **2026-03-13:** Implemented smart `includeStats` parameter for API
- ✅ **2026-03-01:** Completed Redis caching rollout
- ✅ **2026-02-15:** Migrated from MongoDB to PostgreSQL

---

## 🔗 Related Resources

### External Documentation
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [LangChain Docs](https://python.langchain.com/)
- [Gemini API Docs](https://ai.google.dev/gemini-api/docs)
- [pgvector Docs](https://github.com/pgvector/pgvector)

### Project Files
- [README.md](../../README.md) - Project README
- [SECURITY_FIXES.md](SECURITY_FIXES.md) - Security updates and fixes
- [DEPLOYMENT_SECURITY.md](DEPLOYMENT_SECURITY.md) - Deployment security guide
- [.claude/project-info.md](../../.claude/project-info.md) - Project conventions

---

## 📞 Support

For questions about documentation:
- Check this index first
- Review the specific document
- Ask in team chat if unclear

For documentation updates:
- Create a PR with changes
- Update "Last Updated" date
- Add entry to this index if new file

---

*This documentation is maintained by the Kitabim.ai development team.*
*All documents are located in `/docs` as per project conventions.*
