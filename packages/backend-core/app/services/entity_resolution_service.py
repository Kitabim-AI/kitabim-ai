"""Global entity resolution — one algorithm, parameterized by scope (fiction resolves
within a book, non-fiction resolves across the library). See
docs/feature/rag-retrieval-reranking-hybrid-search/knowledge-graph-entity-resolution-design-v2.md §4.

Used both by the background `graph_resolution_job` (worker) and directly by admin
merge/split endpoints (backend), so merge/split execution + audit logging + query-time
cache population happen in exactly one place regardless of caller.
"""

from __future__ import annotations

import difflib
import json
import logging
import math
import unicodedata
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.prompts import ENTITY_RESOLUTION_JUDGE_PROMPT
from app.core import cache_config
from app.db.repositories.graph_repository import GraphRepository
from app.db.repositories.graph_resolution_repository import (
    GraphMergeLogRepository,
    GraphResolutionQueueRepository,
    GraphResolutionReviewsRepository,
)
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.cache_service import cache_service
from app.utils.observability import log_json

from google import genai
from google.genai import types

logger = logging.getLogger("app.services.entity_resolution")

# Hard constraint checks are exact-match on resolved facts; anything above this is a
# strong graded-signal merge, anything below is a confident "leave separate". Between
# the two, the gray-zone LLM judge makes the call.
STRONG_MERGE_SCORE = 0.75
STRONG_LEAVE_SCORE = 0.25
GRAY_ZONE_CONFIDENCE_THRESHOLD = 0.75

TITLES_HONORIFICS = {"شاخ", "خان", "سۇلتان", "بەگ", "ھاجى", "میرزا", "مىرزا", "شاھ"}


def _expand_name_components(raw_aliases: List[str]) -> List[str]:
    """Decomposes canonical names and aliases into distinct component tokens (Item B2).
    Filters out common title/honorific tokens and short words (<3 chars).
    """
    expanded = list(raw_aliases)
    for a in raw_aliases:
        if not a:
            continue
        parts = [p.strip() for p in a.split()]
        if len(parts) > 1:
            for p in parts:
                norm_p = normalize_alias(p)
                if len(norm_p) >= 3 and norm_p not in TITLES_HONORIFICS:
                    expanded.append(p)
    return list(dict.fromkeys([a for a in expanded if a]))


class EntityResolutionVerdict(BaseModel):
    verdict: Literal["same", "different", "unsure"]
    confidence: float
    reasoning: str


def normalize_alias(alias: str) -> str:
    return unicodedata.normalize("NFC", alias).strip().lower()


def _name_similarity(a: Optional[str], b: Optional[str]) -> float:
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, normalize_alias(a), normalize_alias(b)).ratio()


def cosine_similarity(
    a: Optional[List[float]], b: Optional[List[float]]
) -> Optional[float]:
    """Returns the cosine similarity of two equal-length vectors, or None if either is
    missing/empty or their lengths don't match (e.g. one predates a model change)."""
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return None
    return dot / (norm_a * norm_b)


def build_entity_profile_text(entity_data: Dict[str, Any]) -> str:
    """Builds the normalized text an entity's semantic `profile_embedding` (Item 8,
    knowledge-graph-improvement-backlog.md) is computed from: canonical name, aliases,
    subtype/type, and context summary. Used both when embedding freshly extracted
    entities (`embed_and_store_entity_profiles`, called from knowledge_graph_job) and
    when re-embedding a merge-log snapshot for offline evaluation
    (scripts/eval_entity_semantic_matching.py) — the two must build text identically
    or evaluated similarity scores won't reflect what resolution actually saw.
    """
    parts = [entity_data.get("canonical_name") or ""]
    parts.extend(entity_data.get("aliases") or [])
    if entity_data.get("subtype"):
        parts.append(entity_data["subtype"])
    elif entity_data.get("type"):
        parts.append(entity_data["type"])
    if entity_data.get("context_summary"):
        parts.append(entity_data["context_summary"])
    return " — ".join(p for p in parts if p)


async def embed_and_store_entity_profiles(
    graph_repo: GraphRepository,
    entities: List[Dict[str, Any]],
    embeddings_model: Any,
) -> None:
    """Embeds each entity's profile text (`build_entity_profile_text`) and stores it
    as `profile_embedding` on its Neo4j node — the write side of Item 8. Never raises
    on a count mismatch; logs and skips the store instead, since a partial/misaligned
    write would silently corrupt which embedding belongs to which entity.
    `embeddings_model` must expose `aembed_documents(texts: list[str]) -> list[list[float]]`
    (the `EmbeddingProvider` protocol / `GeminiEmbeddings`).
    """
    if not entities:
        return
    texts = [build_entity_profile_text(e) for e in entities]
    vectors = await embeddings_model.aembed_documents(texts)
    if len(vectors) != len(entities):
        log_json(
            logger,
            logging.WARNING,
            "entity profile embedding count mismatch — skipping store",
            expected=len(entities),
            got=len(vectors),
        )
        return
    profile_data = [
        {"id": e["id"], "embedding": vec} for e, vec in zip(entities, vectors) if vec
    ]
    if profile_data:
        await graph_repo.store_profile_embeddings_bulk(profile_data)


def _check_hard_constraints(
    entity_facts: Dict[str, Any], candidate_facts: Dict[str, Any]
) -> str:
    """Returns 'conflict' | 'match' | 'none' (facts too sparse to compare either way)."""
    e_parents = {
        c["parent_id"] for c in entity_facts.get("child_of", []) if c.get("parent_id")
    }
    c_parents = {
        c["parent_id"]
        for c in candidate_facts.get("child_of", [])
        if c.get("parent_id")
    }
    if e_parents and c_parents:
        return "conflict" if e_parents.isdisjoint(c_parents) else "match"

    e_born = {
        b["location_id"]
        for b in entity_facts.get("born_in", [])
        if b.get("location_id")
    }
    c_born = {
        b["location_id"]
        for b in candidate_facts.get("born_in", [])
        if b.get("location_id")
    }
    if e_born and c_born:
        return "conflict" if e_born.isdisjoint(c_born) else "match"

    return "none"


def _graded_score(
    entity: Dict[str, Any],
    candidate: Dict[str, Any],
    entity_facts: Dict[str, Any],
    candidate_facts: Dict[str, Any],
    hard_match: bool = False,
    semantic_weight: float = 0.0,
) -> float:
    """Name/alias similarity + relationship-neighborhood overlap + weak subtype hint +
    discounted shared-parent boost, roughly normalized to 0.0-1.0.

    When `semantic_weight` > 0 and both entities carry a `profile_embedding` (Item 8),
    a semantic-similarity term is blended in, scaled down proportionally from the
    other three signals so the total stays in [0, 1]. Falls back to the original
    three-signal formula, byte-for-byte, when the weight is 0 (the default) or either
    embedding is missing.
    """
    name_score = max(
        _name_similarity(entity.get("canonical_name"), candidate.get("canonical_name")),
        max(
            (
                _name_similarity(a, b)
                for a in [entity.get("canonical_name"), *(entity.get("aliases") or [])]
                for b in [
                    candidate.get("canonical_name"),
                    *(candidate.get("aliases") or []),
                ]
            ),
            default=0.0,
        ),
    )

    e_neighbors = {
        n["neighbor_id"]
        for n in entity_facts.get("neighbors", [])
        if n.get("neighbor_id")
    }
    c_neighbors = {
        n["neighbor_id"]
        for n in candidate_facts.get("neighbors", [])
        if n.get("neighbor_id")
    }
    neighbor_score = 0.0
    if e_neighbors or c_neighbors:
        neighbor_score = len(e_neighbors & c_neighbors) / max(
            len(e_neighbors | c_neighbors), 1
        )

    subtype_score = (
        1.0
        if entity.get("subtype") and entity.get("subtype") == candidate.get("subtype")
        else 0.0
    )

    semantic_score = None
    if semantic_weight > 0.0:
        semantic_score = cosine_similarity(
            entity.get("profile_embedding"), candidate.get("profile_embedding")
        )

    if semantic_score is not None:
        lexical_weight = 1.0 - semantic_weight
        base_score = (
            lexical_weight * 0.55 * name_score
            + lexical_weight * 0.35 * neighbor_score
            + lexical_weight * 0.10 * subtype_score
            + semantic_weight * semantic_score
        )
    else:
        base_score = 0.55 * name_score + 0.35 * neighbor_score + 0.10 * subtype_score

    # Item 3: Shared parent is a supporting signal, not an auto-merge.
    # Discount shared parent if neighbor degree indicates a high-degree hub ancestor.
    if hard_match:
        max_degree = max(len(e_neighbors), len(c_neighbors))
        # High degree hub (e.g. >10 connections to prominent ancestor) receives discounted boost
        parent_boost = 0.05 if max_degree > 10 else 0.15
        base_score = min(1.0, base_score + parent_boost)

    return round(base_score, 4)


def _entity_summary_for_judge(
    entity: Dict[str, Any], facts: Dict[str, Any]
) -> Dict[str, Any]:
    return {
        "canonical_name": entity.get("canonical_name"),
        "aliases": entity.get("aliases") or [],
        "type": entity.get("type"),
        "subtype": entity.get("subtype"),
        "child_of": facts.get("child_of", []),
        "born_in": facts.get("born_in", []),
        "died_in": facts.get("died_in", []),
        "neighbor_names": [
            n.get("neighbor_name")
            for n in facts.get("neighbors", [])
            if n.get("neighbor_name")
        ][:10],
    }


async def _gray_zone_judge(
    entity: Dict[str, Any],
    candidate: Dict[str, Any],
    entity_facts: Dict[str, Any],
    candidate_facts: Dict[str, Any],
    config_repo: SystemConfigsRepository,
) -> EntityResolutionVerdict:
    """Single-shot structured LLM call (raw generate_content, not ADK Agent — matches
    the project convention in app/services/rag/judge.py). Defaults to 'unsure' with
    zero confidence on any failure so a bad LLM call always routes to human review
    rather than silently merging or silently leaving separate.
    """
    model = await config_repo.get_value(
        "gemini_entity_resolution_model", "gemini-3.1-flash-lite"
    )
    prompt = ENTITY_RESOLUTION_JUDGE_PROMPT.format(
        entity_a=json.dumps(
            _entity_summary_for_judge(entity, entity_facts), ensure_ascii=False
        ),
        entity_b=json.dumps(
            _entity_summary_for_judge(candidate, candidate_facts), ensure_ascii=False
        ),
    )
    try:
        client = genai.Client(api_key=settings.gemini_api_key)
        response = await client.aio.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EntityResolutionVerdict,
                temperature=0.0,
            ),
        )
        return EntityResolutionVerdict.model_validate_json(response.text)
    except Exception as exc:
        log_json(
            logger,
            logging.WARNING,
            "entity resolution gray-zone judge call failed — defaulting to unsure",
            error=str(exc),
        )
        return EntityResolutionVerdict(
            verdict="unsure", confidence=0.0, reasoning=f"judge call failed: {exc}"
        )


async def update_alias_cache(graph_repo: GraphRepository, entity_id: str) -> None:
    """Recomputes the (alias -> [entity_id]) Redis lookup for one entity after any
    merge/split/unmerge/resolution outcome touching it (§6). Query time is a lookup
    against this cache, never a live disambiguation call.
    """
    entity = await graph_repo.get_entity_by_id(entity_id)
    if not entity:
        return
    raw_aliases = list(
        dict.fromkeys([entity.get("canonical_name"), *(entity.get("aliases") or [])])
    )
    aliases = _expand_name_components(raw_aliases)
    for alias in aliases:
        if not alias:
            continue
        key = cache_config.KEY_GRAPH_ALIAS_LOOKUP.format(alias=normalize_alias(alias))
        existing = await cache_service.get(key) or []
        ids = list(dict.fromkeys([*existing, entity_id]))
        await cache_service.set(key, ids, ttl=settings.cache_ttl_rag_query)


async def execute_merge(
    session: AsyncSession,
    graph_repo: GraphRepository,
    keep_id: str,
    remove_id: str,
    performed_by: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Optional[int]:
    """Merges `remove_id` into `keep_id`: snapshots `remove_id` to `graph_merge_log`
    BEFORE deleting it, redirects edges via GraphRepository.merge_entities_by_id,
    cleans up `remove_id`'s resolution-queue row, resolves pending review findings for `remove_id`,
    re-queues CHILD_OF children of either node (re-propagation, §4 step 4), and refreshes the alias cache.

    Returns the new `graph_merge_log` row's id (pass to `execute_unmerge` to revert),
    or None (no-op) if either entity no longer exists.
    """
    queue_repo = GraphResolutionQueueRepository(session)
    reviews_repo = GraphResolutionReviewsRepository(session)
    merge_log_repo = GraphMergeLogRepository(session)
    config_repo = SystemConfigsRepository(session)

    keep = await graph_repo.get_entity_by_id(keep_id)
    remove = await graph_repo.get_entity_by_id(remove_id)
    if not keep or not remove:
        return None

    # Clean up dangling Redis alias pointers for the removed entity (Item B2 cleanup)
    remove_raw_aliases = list(
        dict.fromkeys([remove.get("canonical_name"), *(remove.get("aliases") or [])])
    )
    remove_alias_keys = _expand_name_components(remove_raw_aliases)
    for alias in remove_alias_keys:
        if not alias:
            continue
        key = cache_config.KEY_GRAPH_ALIAS_LOOKUP.format(alias=normalize_alias(alias))
        existing = await cache_service.get(key) or []
        if remove_id in existing:
            remaining = [eid for eid in existing if eid != remove_id]
            if remaining:
                await cache_service.set(
                    key, remaining, ttl=settings.cache_ttl_rag_query
                )
            else:
                await cache_service.delete(key)

    edges = await graph_repo.get_entity_edges_snapshot(remove_id)
    merge_log_entry = await merge_log_repo.log_merge(
        kept_entity_id=keep_id,
        removed_entity_id=remove_id,
        removed_entity_snapshot=remove,
        removed_edges_snapshot=edges,
        performed_by=performed_by,
    )

    combined_aliases = list(
        dict.fromkeys(
            [
                *(keep.get("aliases") or []),
                remove.get("canonical_name"),
                *(remove.get("aliases") or []),
            ]
        )
    )
    combined_aliases = [
        a for a in combined_aliases if a and a != keep.get("canonical_name")
    ]

    children_of_remove = await graph_repo.get_children_via_child_of(remove_id)
    children_of_keep = await graph_repo.get_children_via_child_of(keep_id)

    await graph_repo.merge_entities_by_id(keep_id, remove_id, combined_aliases, edges)
    await queue_repo.delete_by_entity_id(remove_id)
    await reviews_repo.resolve_reviews_for_merge(
        keep_id=keep_id, remove_id=remove_id, reviewed_by=user_id or performed_by
    )

    max_passes = int(await config_repo.get_value("resolution_max_passes", "5"))
    for child_id in dict.fromkeys([*children_of_remove, *children_of_keep]):
        await queue_repo.requeue_or_cap(child_id, max_passes)

    await update_alias_cache(graph_repo, keep_id)

    log_json(
        logger,
        logging.INFO,
        "entity merge executed",
        keep_id=keep_id,
        remove_id=remove_id,
        performed_by=performed_by,
        merge_log_id=merge_log_entry.id,
    )
    return merge_log_entry.id


async def execute_split(
    graph_repo: GraphRepository, entity_id: str, split_point_edge_id: str
) -> Dict[str, Any]:
    """Thin wrapper around GraphRepository.split_entities that also refreshes the
    alias cache for both the original and (if created) the new node."""
    result = await graph_repo.split_entities(entity_id, split_point_edge_id)
    await update_alias_cache(graph_repo, entity_id)
    if result.get("new_entity_id"):
        await update_alias_cache(graph_repo, result["new_entity_id"])
    return result


async def execute_unmerge(
    session: AsyncSession, graph_repo: GraphRepository, merge_log_id: int
) -> Dict[str, Any]:
    """Reverts a merge by merge_log_id: recreates the removed node from its snapshot,
    re-points its original edges (matched by stable edge id) back onto it, and marks
    the log row reverted. See design v2 §5 for the known citation-provenance gap on
    edges that collided with a pre-existing edge on the kept node during the merge.
    """
    merge_log_repo = GraphMergeLogRepository(session)
    entry = await merge_log_repo.get(merge_log_id)
    if not entry:
        raise ValueError(f"Merge log entry '{merge_log_id}' does not exist.")
    if entry.reverted_at:
        raise ValueError(f"Merge log entry '{merge_log_id}' was already reverted.")

    unrecoverable = await graph_repo.restore_entity_from_snapshot(
        entry.removed_entity_snapshot, entry.removed_edges_snapshot
    )
    await merge_log_repo.mark_reverted(merge_log_id)
    await update_alias_cache(graph_repo, entry.kept_entity_id)
    await update_alias_cache(graph_repo, str(entry.removed_entity_id))

    log_json(
        logger,
        logging.INFO,
        "entity unmerge executed",
        merge_log_id=merge_log_id,
        restored_entity_id=str(entry.removed_entity_id),
        unrecoverable_edge_count=len(unrecoverable),
    )
    return {
        "restored_entity_id": str(entry.removed_entity_id),
        "unrecoverable_edge_ids": unrecoverable,
    }


async def resolve_entity(
    session: AsyncSession, graph_repo: GraphRepository, entity_id: str
) -> None:
    """Resolves one claimed `graph_resolution_queue` row end-to-end (§4 steps 0-5):
    existence check, candidate selection, per-candidate decision, merge/leave/review
    execution, re-propagation, and finally marking the row succeeded/needs_review/failed.
    """
    queue_repo = GraphResolutionQueueRepository(session)
    reviews_repo = GraphResolutionReviewsRepository(session)
    config_repo = SystemConfigsRepository(session)

    entity = await graph_repo.get_entity_by_id(entity_id)
    if not entity:
        # Step 0: stale queue row pointing at a Neo4j node that no longer exists
        # (crash mid-merge, or deleted via another path, e.g. delete_book_graph).
        await queue_repo.mark_status(entity_id, "failed")
        return

    scope = entity.get("scope")
    book_id = entity.get("book_id")
    similarity_threshold = int(
        await config_repo.get_value("resolution_similarity_threshold", "2")
    )
    semantic_matching_enabled = (
        await config_repo.get_value("entity_semantic_matching_enabled", "false")
    ).strip().lower() == "true"
    semantic_weight = (
        float(await config_repo.get_value("entity_semantic_weight", "0.15"))
        if semantic_matching_enabled
        else 0.0
    )

    await graph_repo.set_resolution_status(entity_id, "resolving")

    candidates = await graph_repo.find_resolution_candidates(
        entity_id=entity_id,
        canonical_name=entity.get("canonical_name"),
        aliases=entity.get("aliases"),
        scope=scope,
        book_id=book_id,
        edit_distance=similarity_threshold,
    )

    if semantic_matching_enabled and entity.get("profile_embedding"):
        candidate_limit = int(
            await config_repo.get_value("entity_semantic_candidate_limit", "5")
        )
        semantic_candidates = await graph_repo.find_semantic_candidates(
            entity_id=entity_id,
            embedding=entity["profile_embedding"],
            scope=scope,
            book_id=book_id,
            limit=candidate_limit,
        )
        seen_ids = {c["id"] for c in candidates}
        candidates = candidates + [
            c for c in semantic_candidates if c["id"] not in seen_ids
        ]

    entity_facts = await graph_repo.get_entity_facts(entity_id)
    review_created = False

    for candidate in candidates:
        candidate_id = candidate["id"]
        current_candidate = await graph_repo.get_entity_by_id(candidate_id)
        if not current_candidate:
            continue  # merged away by an earlier iteration of this same loop

        candidate_facts = await graph_repo.get_entity_facts(candidate_id)
        hard = _check_hard_constraints(entity_facts, candidate_facts)

        if hard == "conflict":
            continue  # hard-constraint split signal: leave separate, next candidate

        score = _graded_score(
            entity,
            current_candidate,
            entity_facts,
            candidate_facts,
            hard_match=(hard == "match"),
            semantic_weight=semantic_weight,
        )
        if score >= STRONG_MERGE_SCORE:
            decision = "merge"
        elif score <= STRONG_LEAVE_SCORE:
            decision = "leave"
        else:
            verdict = await _gray_zone_judge(
                entity, candidate, entity_facts, candidate_facts, config_repo
            )
            evidence = {
                "graded_score": score,
                "hard_constraint": hard,
                "verdict": verdict.verdict,
                "confidence": verdict.confidence,
                "reasoning": verdict.reasoning,
                "entity_a_name": entity.get("canonical_name"),
                "entity_b_name": candidate.get("canonical_name"),
            }
            if (
                verdict.verdict == "same"
                and verdict.confidence >= GRAY_ZONE_CONFIDENCE_THRESHOLD
            ):
                decision = "merge"
            elif (
                verdict.verdict == "different"
                and verdict.confidence >= GRAY_ZONE_CONFIDENCE_THRESHOLD
            ):
                decision = "leave"
            else:
                suggested_action = (
                    "merge"
                    if verdict.verdict == "same"
                    else ("split" if verdict.verdict == "different" else "unsure")
                )
                await reviews_repo.create_review(
                    entity_id, candidate_id, scope, evidence, suggested_action
                )
                review_created = True
                decision = "review"

        if decision == "merge":
            await execute_merge(
                session,
                graph_repo,
                keep_id=entity_id,
                remove_id=candidate_id,
                performed_by="system:resolution_job",
            )
            entity_facts = await graph_repo.get_entity_facts(entity_id)
        elif decision == "review":
            break
        # decision == "leave": fall through to the next candidate

    if review_created:
        await queue_repo.mark_status(entity_id, "needs_review")
        return

    await graph_repo.set_resolution_status(entity_id, "resolved")
    await queue_repo.mark_status(entity_id, "succeeded")
    await update_alias_cache(graph_repo, entity_id)
