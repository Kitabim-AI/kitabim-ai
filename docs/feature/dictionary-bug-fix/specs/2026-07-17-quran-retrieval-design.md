# Quran Retrieval Integration Design (Approach 1)

This design document outlines the integration of Quranic ayah vector search directly into the shared retrieval layer (`vector_search`) to ensure both deterministic and non-deterministic RAG paths retrieve Quranic references when a user asks questions about Islam or the Quran.

## Problem Description
Currently, queries about Islam or the Quran only target the Quran table if they are explicitly routed to the Quran intent pathway (which checks for a narrow set of Quranic keywords like "surah" or "ayah"). General questions about Islam or the Quran (e.g., "What are the rules of fasting?" or "What is the meaning of Islam?") fall back to general book chunk searches and do not retrieve the actual scriptural text of the Quran. 

To resolve this, we will update the search behavior so that when the RAG system performs a vector search on book chunks for an Islamic query, it also queries the `quran` table's ayah embeddings, merges the results, and sorts the combined context by relevance (similarity).

## Proposed Changes

### 1. [packages/backend-core/app/services/rag/utils.py](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/rag/utils.py)
Introduce a utility helper `is_islam_or_quran_query(question: str) -> bool` to perform substring checks on a comprehensive set of unambiguous Islamic terms in both Uyghur and English:
- **Uyghur**: `"قۇرئان"`, `"سۈرە"`, `"ئايەت"`, `"ئاللاھ"`, `"خۇدا"`, `"پەرۋەردىگار"`, `"پەيغەمبەر"`, `"مۇھەممەد"`, `"ئىسلام"`, `"مۇسۇلمان"`, `"ناماز"`, `"روزا"`, `"زاكات"`, `"ھەج"`, `"ھەدىس"`, `"شەرىئەت"`
- **English**: `"quran"`, `"koran"`, `"surah"`, `"ayah"`, `"verse"`, `"allah"`, `"prophet"`, `"muhammad"`, `"islam"`, `"muslim"`, `"ramadan"`, `"hadith"`, `"sharia"`

### 2. [packages/backend-core/app/services/rag/retrieval.py](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/rag/retrieval.py)
Modify `vector_search` to:
- Run `is_islam_or_quran_query` on `ctx.question` and/or `ctx.enriched_question`.
- If true, run a vector similarity query on the `quran` table using `ctx.session` and the computed `query_vector`:
  ```sql
  SELECT 
      id, surah, surah_name_en, surah_name_ar, surah_name_ug,
      ayah, text_ar, text_en, text_ug,
      1 - (embedding::halfvec(3072) <=> CAST(:embedding AS halfvec(3072))) AS similarity
  FROM quran
  WHERE embedding IS NOT NULL
  ORDER BY embedding::halfvec(3072) <=> CAST(:embedding AS halfvec(3072))
  LIMIT :limit
  ```
- Filter Quran matches by the standard threshold (e.g., `similarity > 0.35`).
- Map Quran matches to match the chunk search schema:
  - `book_id`: `"quran"`
  - `title`: `row.surah_name_ug`
  - `surah_name_en`: `row.surah_name_en`
  - `surah_name_ar`: `row.surah_name_ar`
  - `surah`: `row.surah`
  - `ayah`: `row.ayah`
  - `page`: `row.ayah`
  - `volume`: `row.surah`
  - `author`: `"Holy Quran"`
  - `text`: `f"Arabic: {row.text_ar}\nUyghur Translation: {row.text_ug}\nEnglish Translation: {row.text_en}"`
  - `score`: `row.similarity`
- Merge the mapped Quran results with book chunk results, sort by similarity score descending, and slice to the requested `limit`.

### 3. [packages/backend-core/app/services/rag/agent/handler.py](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/rag/agent/handler.py)
Update `_grade_context` to pass through the specific metadata keys for the Quran: `surah`, `ayah`, and `surah_name_en`.

### 4. [packages/backend-core/app/services/rag/answer_builder.py](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/rag/answer_builder.py)
Modify `format_document` to detect `book_id == "quran"` and render the exact expected citation header:
`[Source: Holy Quran, Surah: {title} ({surah_name_en}), Ayah: {ayah}]`

## Verification Plan

### Automated Tests
Run RAG evaluation and test suite:
- `pytest packages/backend-core/tests/app/services/deterministic_router_test.py`
- `pytest packages/backend-core/tests/app/utils/citation_fixer_test.py`

### Manual Verification
Verify that a query like "ئىسلامدىكى بەش پەرز نېمە؟" (What are the five pillars of Islam?) or "قۇرئاندا روزا تۇتۇش ھەققىدە نېمە دېيىلگەن؟" (What is said in the Quran about fasting?) retrieves Quranic verses in both the deterministic router and the ADK Agent, and that the references link correctly to the Quran reader in the frontend.
