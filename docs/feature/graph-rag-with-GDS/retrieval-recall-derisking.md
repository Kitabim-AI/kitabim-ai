# Retrieval Recall De-risking (ADK2 Chat)

This document collects several **independent problems** in the ADK2 chat retrieval path,
grouped into two problem areas. Each problem has its own fix and can be worked on separately.

- **Area A – Summary over-trust:** book discovery hard-scopes the search to summary-picked books.
- **Area B – Graph entity-lookup recall:** the global entity leg misses inflected and partial names.

Reference – scoping of the three retrieval legs inside `search_chunks`:

| Leg | Scoped by summary-picked books? |
|-----|---------------------------------|
| Vector search | Yes |
| Keyword / BM25 (`chunks_repository.keyword_search`) | Yes (same `book_ids`) |
| Graph / entity lookup (`graph_entity_lookup`) | No – global (but see Area B recall gaps) |

Two of three legs are locked to the summary's book choice; only the graph leg escapes it, and
its recall is fragile (Area B).

---

## Area A – Summary over-trust in book discovery

**Problem.** The book-discovery step (`search_books_by_summary`) picks which books to search,
then hard-scopes the passage search to those book IDs. Each book is compressed into one LLM-written
summary and one embedding vector – good at topic/"aboutness" matching, lossy for specific facts,
minor characters, or rare terms. If the summary picks the wrong books, the real answer becomes
invisible to both the vector and keyword legs.

### A1. Add a parallel unscoped keyword leg
Run an unscoped keyword search alongside the scoped hybrid search and fuse it into the results.
`chunks_repository.keyword_search` already supports `book_ids=None` (whole-library mode), so this
reuses the existing query path – no new search needed. Lets rare exact terms bypass the summary
gate while vector search stays scoped for precision.

- Touch point: `services/rag/retrieval.py` (`_search_chunks_hybrid`), fuse via existing RRF.

### A2. Widen recall for fact/passage intents
When the question asks for a specific detail/passage (not a book-level "aboutness" question),
lower the summary similarity threshold or raise the candidate book count so the summary gate is
less likely to exclude the correct book.

- Current defaults: `summary_threshold=0.45`, summary search `limit=20`
  (`core/config.py`, `book_summaries_repository.summary_search`).

### A3. Make the broaden-fallback unconditional for fact questions
Today the whole-library re-search only fires when scoped `search_chunks` returns fewer than 4
results (prompt step 6h). For fact questions, fire the whole-library re-search unconditionally so
a wrongly-scoped set that returns 4+ mediocre passages can't quietly win.

- Touch point: `services/rag/agent/prompts.py` (step 6h) and/or deterministic path.

---

## Area B – Graph entity-lookup recall

**Problem.** The graph leg (`graph_entity_lookup` in `services/rag/retrieval.py`) is the only leg
not scoped by the summary, so it is the natural escape hatch – but its recall is fragile because
matching is an **exact Redis alias key lookup**: the query word must equal a stored alias
character-for-character after light normalization (`normalize_alias` = NFC + trim + lowercase,
`entity_resolution_service.py`). Two distinct failure modes:

### B1. Suffix mismatch – prefix enumeration (rule-free)
User types an inflected form (`پابۇرنىڭ`, `يۈنۈسخاننىڭ`, `بابۇرنىڭ`) but the graph stored the bare name
(`پابۇر`, `يۈنۈسخان`, `بابۇر`). Uyghur is agglutinative, so the surface word is `stem + suffix` and the
stored name is a **prefix** of it.

- **Do NOT hardcode suffix-stripping rules** – Uyghur morphology (vowel-harmony allomorphs, stem
  mutation) makes hand-written strip rules fragile and high-maintenance.
- **Instead, enumerate prefixes of the query word** (longest → shortest, down to a min length
  ≥3-4) and do an exact cache lookup for each. The cache decides which prefix is a real alias; a
  non-name prefix simply isn't a key, so there are no false strips. Take the longest hit; let the
  answer LLM disambiguate ties.
- Keeps the zero-latency design – every prefix is still an O(1) exact key lookup.
- Touch point: `graph_entity_lookup` candidate generation in `services/rag/retrieval.py`.

### B2. Partial name – index name parts as aliases (write side)
User types a short form (`بابۇر`) but the graph stored the full canonical name
(`زەھىرىددىن مۇھەممەد بابۇر`). Exact/prefix lookup can't match a token that sits *inside* a longer
stored name.

- **Decompose canonical names into distinctive component aliases at write time** (index `بابۇر`
  as its own alias). Read path stays an exact key lookup – no latency change.
- **Drop title/stopword tokens** (`شاخ`/King, `خان`, `بەگ`, very common given names) so ambiguous
  fragments don't over-match. The answer LLM already disambiguates multiple entity matches.
- Touch point: alias cache population in `services/entity_resolution_service.py`.

**Related cleanup – invalidate removed-entity alias keys on merge.** `update_alias_cache` only
*unions* IDs into an alias key, never removes them (`entity_resolution_service.py`). On
`execute_merge`, the removed entity's ID is deleted from Neo4j but lingers in its alias cache
keys as a dangling pointer until the key's TTL (`cache_ttl_rag_query`) expires – so a matching
query does a wasted Neo4j fact-fetch for a dead ID, and the alias briefly resolves to two IDs
(one non-existent). Functionally safe (dead-ID fetch returns nothing, errors are caught), but not
clean. Fix: in `execute_merge`, explicitly rewrite/`cache_service.delete` the removed entity's
alias keys (or drop the dead ID from any key it still appears in) rather than waiting for TTL.
This becomes more important once B2 adds more alias keys per entity.

**Required read-side rule – prefer the most-complete match (first+last-name ambiguity).**
Component aliases increase false matches when the query gives a full name but the graph holds
separate single-name entities. Example: query `زەھىرىددىن بابۇر` with entities X (`زەھىرىددىن`
only), Y (`بابۇر` only), and Z (`زەھىرىددىن مۇھەممەد بابۇر`), aliases include both. The current
union logic returns X + Y + Z – injecting facts about an unrelated Zahiriddin and an unrelated
Babur as noise. B2 must therefore ship WITH this read-side resolution rule, not raw aliases:

1. **Prefer the entity matching the MOST query name-tokens** (token-intersection over union).
   Z covers both tokens; X and Y cover one each → keep Z, drop the single-token-only matches.
2. **Prefer phrase/bigram matches** – if the bigram `زەھىرىددىن بابۇر` resolves to a single
   entity, weight it highest and suppress its single-token constituents.
3. **Fall back to single-token union only when no multi-token match exists** (user typed one name).
4. **Score by specificity** – graph hits are currently a flat `score=0.9` (`retrieval.py`); give
   full-name/multi-token matches a higher score than single-token matches so the reranker/answer
   LLM weighs the complete match above stray single-token noise.
5. **Stopword/common-name filter (shared with B2 above)** – never index hyper-common given names
   (`مۇھەممەد`, `ئەھمەد`) as standalone aliases; the first+last case is the main reason it matters.

Genuine ambiguity (two real "Zahiriddin Babur"s) still falls through to the answer LLM tiebreaker,
which is the existing designed behavior.

**How to identify hyper-common names – measure, don't hardcode.** Deriving "common-ness" from a
curated name list is the same fragility trap as hardcoded suffix rules. Instead use
**entity document frequency (IDF)**: for each name-part token, count how many DISTINCT entities
carry it in their `canonical_name`/`aliases`. A token in many entities (`مۇھەممەد` → 200 entities)
is non-distinctive; a token in few (`بابۇر` → 3) is distinctive. This is computable from the Neo4j
`aliases`/`canonical_name` already stored (or an incremental token→entity-count map), and it
self-adapts as the graph grows. Two ways to apply it:

- **Soft (preferred): IDF weighting at query time** – index every name-part but weight each match
  by inverse entity-frequency, so a `بابۇر` match scores high and a `مۇھەممەد` match scores near
  zero. No threshold cliff, and it *is* the "score by specificity" rule (#4) – one mechanism.
- **Hard: frequency-threshold filter at write time** – skip indexing any name-part above a
  frequency percentile. Simpler but a cliff; a name just over the line is fully excluded.

Optional backstop: a **tiny title/honorific list** (`شاخ`, `خان`, `سۇلتان`, `بەگ`, `ھاجى`) – titles
are non-names regardless of frequency. Keep it to titles only; let IDF handle given names, since
curating those is where language complexity bites.

### B3. Residual fallback (covers both B1 + B2)
Stem mutation, typos, and odd spellings survive both B1 and B2. Cover them with the existing Neo4j
Lucene fuzzy full-text index (`entity_search_idx`, `graph_repository.py`) as a **miss-only**
fallback – invoked only when the exact/prefix cache lookup fails, gated to entity-like tokens, so
per-query Neo4j latency stays contained.

- Do NOT use fuzzy edit-distance as the *primary* suffix fix – Uyghur suffixes (2-4 chars) exceed
  typical edit-distance thresholds and cause false matches. Prefer B1 for suffixes.

---

## Area C – Application security

**Context.** Separate from the retrieval work above; captured here as tracked de-risking items
from a security review of the auth, API, and deploy paths. The overall posture is strong
(JWT with key rotation, PKCE OAuth with signed-state CSRF + open-redirect checks, in-memory
access token + `httpOnly` refresh cookie, whitelisted CORS, security headers, bound-param SQL,
size/type/decompression-bomb-guarded uploads). The items below are residual gaps.

### C1. Timing-unsafe operator-token comparison
`verify_operator_access` compares the operator token with `==`, which leaks length/prefix via
response timing. Use `secrets.compare_digest(...)` for a constant-time comparison.

- Touch point: `services/backend/api/endpoints/cache_router.py` (`verify_operator_access`).

### C2. Production error leakage depends on `ENVIRONMENT`
The global exception handler returns `str(exc)` whenever `ENVIRONMENT != "production"`, and the
default is `"development"`. If the prod deployment doesn't explicitly set `ENVIRONMENT=production`,
stack-trace details leak to clients. Verify the deploy env sets it (and consider failing closed).

- Touch point: `services/backend/main.py` (`global_exception_handler`), `core/config.py`
  (`environment` default), `deploy/gcp/.env`.

### C3. CSP allows `script-src 'unsafe-inline'`
The response CSP permits inline scripts because the OAuth success page injects an inline script.
This weakens XSS defense. Move to a nonce-based CSP for those responses so `'unsafe-inline'` can
be dropped from `script-src`.

- Touch point: `services/backend/main.py` (`add_security_headers`), OAuth HTML in
  `api/endpoints/auth_router.py` (`_success_response`).

### C4. Dynamic interval string in SQL (defense-in-depth)
`revert_stuck_issues` builds `text(f"interval '{timeout_minutes} minutes'")`. `timeout_minutes` is
internal/int today (not exploitable), but string-interpolating into SQL is an anti-pattern. Bind it
instead (e.g. `make_interval(mins => :m)` or `:m * interval '1 minute'`).

- Touch point: `packages/backend-core/app/services/auto_correct_service.py`.

### C5. `file.filename` assumed non-null in upload
`upload_pdf` calls `file.filename.lower()`; a multipart part without a filename yields `None` and
raises a 500. Guard for a missing filename and return a 400 instead.

- Touch point: `services/backend/api/endpoints/books_router.py` (`upload_pdf`).

---

## Status

| ID | Area | Item | Status |
|----|------|------|--------|
| A1 | Summary | Parallel unscoped keyword leg (reuse `keyword_search(book_ids=None)`) | ✅ Implemented |
| A2 | Summary | Widen recall for fact/passage intents | ✅ Implemented |
| A3 | Summary | Unconditional broaden-fallback for fact questions | ✅ Implemented |
| B1 | Graph | Suffix fix via prefix enumeration (no hardcoded rules) | ✅ Implemented |
| B2 | Graph | Partial-name fix via name-part aliases (stopword-filtered) | ✅ Implemented |
| B3 | Graph | Miss-only Neo4j fuzzy fallback for residual cases | ✅ Implemented |
| C1 | Security | Constant-time operator-token compare (`secrets.compare_digest`) | Proposed |
| C2 | Security | Ensure `ENVIRONMENT=production` in prod deploy (error leakage) | Proposed |
| C3 | Security | Harden CSP – drop `script-src 'unsafe-inline'` via nonce | Proposed |
| C4 | Security | Bind interval param in `auto_correct_service` SQL | Proposed |
| C5 | Security | Null-guard `file.filename` in `upload_pdf` | Proposed |
