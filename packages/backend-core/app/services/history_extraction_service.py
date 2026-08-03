"""Service for extracting and enriching Uyghur historical terms from book pages."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.prompts import (
    EXTRACTION_PROMPT_TEMPLATE,
    FACT_CLASSIFICATION_PROMPT_TEMPLATE,
    SYNTHESIS_PROMPT_TEMPLATE,
)
from app.db.models import SystemConfig
from app.db.repositories.dictionary_repository import DictionaryRepository
from app.services.history_fact_utils import (
    bootstrap_legacy_facts,
    cosine_similarity,
    find_deterministic_duplicate,
    merge_citation,
)

logger = logging.getLogger(__name__)

EMBEDDING_RELATED_THRESHOLD = 0.72


class HistoryFactSynthesisError(Exception):
    """Raised when the definition-synthesis LLM call fails or returns no usable text."""


def _parse_json_object(raw: str) -> Dict[str, Any]:
    """Parse a JSON object from raw LLM text, tolerating markdown code fences."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    return json.loads(match.group())


def _entities_from_parsed(data: Any) -> List[Dict[str, Any]]:
    """Normalize an already-parsed extraction payload into its entities list.
    Models sometimes return the entities array directly instead of the
    requested {"entities": [...]} wrapper — tolerate both shapes rather than
    crashing (a bare list has no .get) or silently dropping the whole batch."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("entities", [])
    return []


def parse_extraction_entities(raw: str) -> List[Dict[str, Any]]:
    """Parse the extraction LLM's raw JSON response into an entities list,
    tolerating markdown code fences and either JSON shape (see
    _entities_from_parsed). Shared by the interactive and Gemini Batch API
    extraction paths so both handle model output the same way."""
    text = raw.strip()
    try:
        return _entities_from_parsed(json.loads(text))
    except json.JSONDecodeError:
        pass
    match = re.search(r"[\{\[].*[\}\]]", text, re.DOTALL)
    if not match:
        return []
    try:
        return _entities_from_parsed(json.loads(match.group()))
    except json.JSONDecodeError:
        return []


class HistoryExtractionService:
    def __init__(self, session: AsyncSession, gemini_client: Any = None):
        self.session = session
        self.repo = DictionaryRepository(session)
        self.gemini_client = gemini_client

    async def _get_system_config_model(self) -> str:
        """Fetch the dynamic history extraction model name from system_config."""
        stmt = select(SystemConfig).where(
            SystemConfig.key == "history_extraction_model"
        )
        res = await self.session.execute(stmt)
        config = res.scalar_one_or_none()
        if config and config.value.strip():
            return config.value.strip()
        return "gemini-2.5-flash"

    async def _get_system_config_batch_size(self) -> int:
        """Fetch the dynamic history extraction batch size from system_config."""
        stmt = select(SystemConfig).where(
            SystemConfig.key == "history_extraction_batch_size"
        )
        res = await self.session.execute(stmt)
        config = res.scalar_one_or_none()
        if config and config.value.strip().isdigit():
            return int(config.value.strip())
        return 15

    async def _get_system_config_embedding_model(self) -> str:
        """Fetch the dynamic embedding model name from system_config."""
        stmt = select(SystemConfig).where(SystemConfig.key == "gemini_embedding_model")
        res = await self.session.execute(stmt)
        config = res.scalar_one_or_none()
        if config and config.value.strip():
            return config.value.strip()
        return "models/gemini-embedding-001"

    async def _call_llm_extraction(
        self, pages_text: str, model_name: str
    ) -> List[Dict[str, Any]]:
        """Call Gemini API for structured JSON extraction."""
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(pages_text=pages_text)
        if self.gemini_client and hasattr(self.gemini_client, "generate_structured"):
            res = await self.gemini_client.generate_structured(prompt, model=model_name)
            return _entities_from_parsed(res)

        # Fallback or standard call via internal LLM service
        try:
            from app.llm.models import generate_text

            raw_res = await generate_text(prompt, model_name=model_name)
            return parse_extraction_entities(raw_res)
        except Exception as e:
            logger.warning(f"LLM extraction call failed: {e}")
            return []

    async def _embed_facts(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of fact texts for tier-2 similarity comparison."""
        from app.llm.models import GeminiEmbeddings

        model_name = await self._get_system_config_embedding_model()
        embeddings = GeminiEmbeddings(model_name=model_name)
        return await embeddings.aembed_documents(texts)

    async def _classify_facts(
        self,
        term: str,
        existing_facts: List[Dict[str, Any]],
        candidates: List[Dict[str, Any]],
        model_name: str,
    ) -> List[Dict[str, Any]]:
        """Ask the LLM to classify each candidate as new/duplicate/conflict against
        the term's existing active facts. Returns [] on any failure — callers must
        treat unresolved candidates as new (never silently drop them)."""
        active_facts = [f for f in existing_facts if f.get("status") == "active"]
        existing_lines = (
            "\n".join(f"[{f['id']}] {f['text']}" for f in active_facts) or "(none)"
        )
        candidate_lines = "\n".join(
            f"({i}) {c['text']}" for i, c in enumerate(candidates)
        )

        prompt = FACT_CLASSIFICATION_PROMPT_TEMPLATE.format(
            term=term, existing_facts=existing_lines, candidate_facts=candidate_lines
        )
        try:
            from app.llm.models import generate_text

            raw = await generate_text(prompt, model_name=model_name)
            data = _parse_json_object(raw)
            return data.get("decisions", [])
        except Exception as exc:
            logger.warning(f"Fact classification LLM call failed: {exc}")
            return []

    async def _merge_facts(
        self,
        term: str,
        existing_facts: List[Dict[str, Any]],
        new_candidates: List[Dict[str, Any]],
        citation_base: Dict[str, Any],
        model_name: str,
    ) -> List[Dict[str, Any]]:
        """Merge newly extracted candidate facts into an existing fact list via the
        three-tier pipeline: deterministic spelling match, embedding similarity,
        then (only for the ambiguous remainder) one LLM classification call."""
        facts = [dict(f) for f in existing_facts]
        next_id = max((f["id"] for f in facts), default=0) + 1
        next_conflict_group = (
            max((f.get("conflict_group") or 0 for f in facts), default=0) + 1
        )

        def _append_new(text: str, citation: Dict[str, Any]) -> None:
            nonlocal next_id
            facts.append(
                {
                    "id": next_id,
                    "text": text,
                    "citations": [citation],
                    "status": "active",
                    "conflict_group": None,
                }
            )
            next_id += 1

        # Tier 1: deterministic spelling-normalized match
        unresolved: List[Dict[str, Any]] = []
        for cand in new_candidates:
            text = (cand.get("text") or "").strip()
            if not text:
                continue
            citation = {**citation_base, "pages": cand.get("pages", [])}

            dup_id = find_deterministic_duplicate(text, facts)
            if dup_id is not None:
                target = next(f for f in facts if f["id"] == dup_id)
                merge_citation(target, citation)
                continue

            unresolved.append({"text": text, "citation": citation})

        if not unresolved:
            return facts

        # Tier 2: embedding similarity — route only "related" candidates to tier 3
        active_facts = [f for f in facts if f.get("status") == "active"]
        related_candidates: List[Dict[str, Any]] = []

        if not active_facts:
            for cand in unresolved:
                _append_new(cand["text"], cand["citation"])
            return facts

        try:
            texts_to_embed = [f["text"] for f in active_facts] + [
                u["text"] for u in unresolved
            ]
            vectors = await self._embed_facts(texts_to_embed)
            existing_vectors = vectors[: len(active_facts)]
            candidate_vectors = vectors[len(active_facts) :]

            for cand, vec in zip(unresolved, candidate_vectors):
                best_score = max(
                    (cosine_similarity(vec, ev) for ev in existing_vectors), default=0.0
                )
                if best_score >= EMBEDDING_RELATED_THRESHOLD:
                    related_candidates.append(cand)
                else:
                    _append_new(cand["text"], cand["citation"])
        except Exception as exc:
            logger.warning(f"Fact embedding similarity check failed: {exc}")
            related_candidates = list(unresolved)

        if not related_candidates:
            return facts

        # Tier 3: structured LLM classification for the ambiguous remainder
        decisions = await self._classify_facts(
            term, facts, related_candidates, model_name
        )
        decided_indices = set()
        for decision in decisions:
            idx = decision.get("candidate_index")
            if (
                idx is None
                or idx in decided_indices
                or not (0 <= idx < len(related_candidates))
            ):
                continue
            decided_indices.add(idx)
            cand = related_candidates[idx]
            outcome = decision.get("decision")
            existing_id = decision.get("existing_fact_id")
            target = (
                next((f for f in facts if f["id"] == existing_id), None)
                if existing_id is not None
                else None
            )

            if outcome == "duplicate" and target is not None:
                merge_citation(target, cand["citation"])
                continue

            if outcome == "conflict" and target is not None:
                if target.get("conflict_group") is None:
                    target["conflict_group"] = next_conflict_group
                    target["status"] = "conflict"
                    next_conflict_group += 1
                facts.append(
                    {
                        "id": next_id,
                        "text": cand["text"],
                        "citations": [cand["citation"]],
                        "status": "conflict",
                        "conflict_group": target["conflict_group"],
                    }
                )
                next_id += 1
                continue

            # "new", or any unrecognized/mistargeted decision: default to a new active fact
            _append_new(cand["text"], cand["citation"])

        # Any candidate the classifier didn't return a decision for (call failed,
        # returned [], or skipped an index) also defaults to new — never dropped.
        for i, cand in enumerate(related_candidates):
            if i not in decided_indices:
                _append_new(cand["text"], cand["citation"])

        return facts

    async def _synthesize_definition(
        self, term: str, facts: List[Dict[str, Any]], model_name: str
    ) -> str:
        """Generate the final Uyghur prose definition from a term's active facts
        in a single LLM call. Never chains against a prior synthesis result."""
        active = [f for f in facts if f.get("status") == "active"]
        if not active:
            return ""

        facts_lines = []
        for f in active:
            citation_bits = ", ".join(
                f"{c.get('book_title', '')} {c.get('pages', [])}"
                for c in f.get("citations", [])
            )
            facts_lines.append(
                f"- {f['text']} ({citation_bits})"
                if citation_bits
                else f"- {f['text']}"
            )
        facts_text = "\n".join(facts_lines)

        prompt = SYNTHESIS_PROMPT_TEMPLATE.format(term=term, facts_text=facts_text)
        try:
            from app.llm.models import generate_text

            raw = await generate_text(prompt, model_name=model_name)
            data = _parse_json_object(raw)
            definition = (data.get("definition") or "").strip()
        except Exception as exc:
            raise HistoryFactSynthesisError(str(exc)) from exc

        if not definition:
            raise HistoryFactSynthesisError(
                f"Synthesis produced an empty definition for term '{term}'"
            )
        return definition

    async def process_book_pages(
        self,
        book_id: str,
        book_title: str,
        pages_data: List[Dict[str, Any]],
        volume: int | None = None,
        min_significance: int = 5,
        batch_size: int | None = None,
        overlap: int = 0,
    ) -> List[Dict[str, Any]]:
        """Process OCR book pages with sliding window and stage candidates."""
        model_name = await self._get_system_config_model()
        if batch_size is None:
            batch_size = await self._get_system_config_batch_size()
        staged_results = []

        if not pages_data:
            return staged_results

        # Sort pages by page_number
        pages_data = sorted(pages_data, key=lambda x: x.get("page_number", 0))

        # Sliding window batching
        i = 0
        while i < len(pages_data):
            batch = pages_data[i : i + batch_size]
            if not batch:
                break

            # Construct pages_text
            text_blocks = []
            for p in batch:
                p_num = p.get("page_number", 0)
                content = p.get("content", "").strip()
                if content:
                    text_blocks.append(f"--- PAGE {p_num} ---\n{content}")

            pages_text = "\n\n".join(text_blocks)
            if pages_text.strip():
                entities = await self._call_llm_extraction(pages_text, model_name)
                for ent in entities:
                    score = ent.get("significance_score", 5)
                    if score < min_significance:
                        continue

                    staged_item = await self._stage_entity(
                        book_id=book_id,
                        book_title=book_title,
                        volume=volume,
                        entity=ent,
                        model_name=model_name,
                    )
                    if staged_item:
                        staged_results.append(staged_item)

            # Move window by (batch_size - overlap)
            step = max(1, batch_size - overlap)
            i += step

        return staged_results

    async def _stage_entity(
        self,
        book_id: str,
        book_title: str,
        volume: int | None,
        entity: Dict[str, Any],
        model_name: str,
        auto_commit: bool = True,
    ) -> Dict[str, Any] | None:
        term = entity.get("term", "").strip()
        if not term:
            return None

        raw_facts = entity.get("facts", [])
        category = entity.get("category", "general")
        score = entity.get("significance_score", 5)
        reason = entity.get("significance_reason", "")
        transliteration = entity.get("transliteration", "")
        letter_group = term[0].upper() if term else "A"
        citation_base = {"book_id": book_id, "book_title": book_title, "volume": volume}

        # Check existing published record or pending staging record
        existing_live = await self.repo.find_matching_history_term(term)
        existing_staging = await self.repo.find_matching_staging_term(term)

        # Do not patch existing non-AI generated history dictionary records
        if existing_live and not existing_live.is_ai_generated:
            logger.info(
                f"Skipping history extraction staging for non-AI generated term '{term}'"
            )
            if not existing_staging:
                return None
            existing_live = None

        if existing_staging:
            # Update existing pending staging candidate in-place (prevents duplicate staging rows)
            merged_facts = await self._merge_facts(
                term, existing_staging.facts, raw_facts, citation_base, model_name
            )
            staged = await self.repo.update_staging_term(
                existing_staging,
                transliteration=transliteration or existing_staging.transliteration,
                category=category or existing_staging.category,
                significance_score=max(score, existing_staging.significance_score),
                significance_reason=reason or existing_staging.significance_reason,
                facts=merged_facts,
            )
        elif existing_live:
            # Incremental enrichment workflow for published AI record
            base_facts = bootstrap_legacy_facts(
                existing_live.facts, existing_live.definition
            )
            merged_facts = await self._merge_facts(
                term, base_facts, raw_facts, citation_base, model_name
            )
            staged = await self.repo.create_staging_term(
                book_id=book_id,
                term=term,
                letter_group=letter_group,
                definition=None,
                transliteration=transliteration or existing_live.transliteration,
                original_definition=existing_live.definition,
                category=category,
                significance_score=score,
                significance_reason=reason,
                is_ai_generated=True,
                entry_type="enrichment",
                existing_dictionary_id=existing_live.id,
                facts=merged_facts,
            )
        else:
            # New candidate
            merged_facts = await self._merge_facts(
                term, [], raw_facts, citation_base, model_name
            )
            staged = await self.repo.create_staging_term(
                book_id=book_id,
                term=term,
                letter_group=letter_group,
                definition=None,
                transliteration=transliteration,
                category=category,
                significance_score=score,
                significance_reason=reason,
                is_ai_generated=True,
                entry_type="new",
                facts=merged_facts,
            )

        if auto_commit:
            await self.session.commit()

        return {
            "id": staged.id,
            "term": staged.term,
            "category": staged.category,
            "significanceScore": staged.significance_score,
            "entryType": staged.entry_type,
        }
