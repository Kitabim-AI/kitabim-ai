"""Service for reviewing history_dictionary_staging candidates and publishing approvals."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.dictionary_repository import DictionaryRepository
from app.models.schemas import HistoryFact

logger = logging.getLogger(__name__)


def _serialize_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Camel-case a raw (snake_case) fact list for API responses, matching the
    shape `HistoryStagingItem.facts` already produces via model_dump(by_alias=True)."""
    return [HistoryFact.model_validate(f).model_dump(by_alias=True) for f in facts]


class StagingConflictsUnresolvedError(Exception):
    """Raised when approving a staging candidate that still has unresolved fact conflicts."""

    def __init__(self, staging_id: int):
        self.staging_id = staging_id
        super().__init__(
            f"Staging candidate {staging_id} has unresolved fact conflicts"
        )


class DictionaryStagingService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = DictionaryRepository(session)

    async def approve_staging_term(self, staging_id: int) -> dict[str, Any] | None:
        """Approve a candidate: synthesize its definition from curated facts,
        insert or update history_dictionary, and mark staging approved."""
        staging = await self.repo.get_staging_term_by_id(staging_id)
        if not staging or staging.status != "pending":
            return None

        if any(f.get("status") == "conflict" for f in staging.facts):
            raise StagingConflictsUnresolvedError(staging_id)

        from app.services.history_extraction_service import HistoryExtractionService

        extraction_service = HistoryExtractionService(self.session)
        model_name = await extraction_service._get_system_config_model()
        definition = await extraction_service._synthesize_definition(
            staging.term, staging.facts, model_name
        )

        target_entry = None
        if staging.existing_dictionary_id:
            target_entry = await self.repo.get_history_dictionary_by_id(
                staging.existing_dictionary_id
            )
        if not target_entry:
            target_entry = await self.repo.get_history_dictionary_by_term(staging.term)

        if target_entry:
            if not target_entry.is_ai_generated:
                logger.info(
                    f"Skipping dictionary entry update for non-AI generated term: '{target_entry.term}'"
                )
            else:
                target_entry = await self.repo.update_history_dictionary_entry(
                    target_entry,
                    definition=definition,
                    transliteration=staging.transliteration
                    or target_entry.transliteration,
                    category=staging.category,
                    significance_score=staging.significance_score,
                    is_ai_generated=True,
                    facts=staging.facts,
                )
        else:
            target_entry = await self.repo.create_history_dictionary_entry(
                term=staging.term,
                transliteration=staging.transliteration,
                definition=definition,
                letter_group=staging.letter_group,
                category=staging.category,
                significance_score=staging.significance_score,
                is_ai_generated=staging.is_ai_generated,
                facts=staging.facts,
            )

        await self.repo.update_staging_term(staging, definition=definition)
        await self.repo.set_staging_status(staging, "approved")
        await self.session.commit()
        await self.session.refresh(target_entry)

        return {
            "id": target_entry.id,
            "term": target_entry.term,
            "transliteration": target_entry.transliteration,
            "definition": target_entry.definition,
            "letterGroup": target_entry.letter_group,
            "category": target_entry.category,
            "significanceScore": target_entry.significance_score,
            "isAiGenerated": target_entry.is_ai_generated,
            "facts": _serialize_facts(target_entry.facts),
        }

    async def reject_staging_term(self, staging_id: int) -> bool:
        """Mark a candidate as rejected."""
        staging = await self.repo.get_staging_term_by_id(staging_id)
        if not staging:
            return False
        await self.repo.set_staging_status(staging, "rejected")
        await self.session.commit()
        return True

    async def resolve_fact(
        self, staging_id: int, fact_id: int, status: str, text: str | None = None
    ) -> dict[str, Any] | None:
        """Resolve a single fact's status on a pending staging candidate (e.g.
        pick a side of a conflict, reject a fact, or edit its text)."""
        staging = await self.repo.get_staging_term_by_id(staging_id)
        if not staging or staging.status != "pending":
            return None

        facts = [dict(f) for f in staging.facts]
        target = next((f for f in facts if f["id"] == fact_id), None)
        if not target:
            return None

        target["status"] = status
        if text is not None:
            target["text"] = text.strip()
            # A cached embedding is only valid for the text it was computed
            # from — drop it so the next merge event re-embeds the edited text
            # instead of comparing against a now-stale vector.
            target.pop("embedding", None)
        if status != "conflict":
            target["conflict_group"] = None

        await self.repo.update_staging_term(staging, facts=facts)
        await self.session.commit()
        return {"id": staging.id, "facts": _serialize_facts(facts)}

    async def synthesize_definition(self, staging_id: int) -> str | None:
        """Regenerate the cached preview `definition` from the candidate's
        current active facts. Never chains against a prior synthesis result."""
        staging = await self.repo.get_staging_term_by_id(staging_id)
        if not staging:
            return None

        from app.services.history_extraction_service import HistoryExtractionService

        extraction_service = HistoryExtractionService(self.session)
        model_name = await extraction_service._get_system_config_model()
        definition = await extraction_service._synthesize_definition(
            staging.term, staging.facts, model_name
        )
        await self.repo.update_staging_term(staging, definition=definition)
        await self.session.commit()
        return definition
