"""ChatOrchestrator — the ADK-native chat orchestrator, the sole chat pipeline"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Optional, Union
from sqlalchemy.ext.asyncio import AsyncSession

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.runners import InMemoryRunner, Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.core.characters import CHARACTERS, DEFAULT_CHARACTER_ID
from app.core.config import settings
from app.db.models import Conversation
from app.db.repositories.books_repository import BooksRepository
from app.db.repositories.conversation_repository import ConversationRepository
from app.db.repositories.rag_evaluations_repository import RAGEvaluationsRepository
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.rag.llm_resources import llm_resources
from app.services.chat.answer_agent import build_answer_agent
from app.services.chat.context import ChatRequestDTO
from app.services.chat.exact_phrase import (
    format_page_hits,
    run_exact_phrase_retrieval,
    summarize_page_hits_as_text,
)
from app.services.chat.history import format_history_for_analysis
from app.services.chat.retrieval_agent import build_retrieval_agent
from app.services.chat.context_grading import (
    _build_human_message,
    _extract_used_book_ids,
    _grade_context,
)
from app.services.chat.query_signals import analyze_query_signals
from app.services.rag.agent.reranker import rerank_context
from app.services.rag.context import QueryContext, set_current_query_context
from app.services.rag.phrase_intent import detect_phrase_intent
from app.services.rag.retrieval import find_books_by_title_in_question
from app.utils.citation_fixer import fix_malformed_citations
from app.utils.observability import log_json

# Fallback default when the rag_keyword_top_k system_config row is missing.
_EXACT_PHRASE_DEFAULT_LIMIT = 10


logger = logging.getLogger("app.services.chat.orchestrator")


def _extract_effective_question(question: str, observations: list[dict]) -> str:
    """Extract standalone rewritten question from observations if rewrite_query was called."""
    for obs in observations:
        if obs.get("tool") == "rewrite_query":
            res = obs.get("result", {})
            if isinstance(res, dict) and res.get("rewritten_question"):
                return res["rewritten_question"]
    return question


class ChatOrchestrator:
    """Orchestrator managing two-agent ADK execution pipeline and session persistence"""

    def __init__(
        self,
        session_service: Optional[Any] = None,
        conversation_repo: Optional[ConversationRepository] = None,
    ):
        self.session_service = session_service
        self.conversation_repo = conversation_repo

    async def stream_response(
        self,
        request_dto: ChatRequestDTO,
        db_session: AsyncSession,
        model_name: str = "gemini-2.5-flash",
    ) -> AsyncIterator[Union[str, dict]]:
        """Execute two-agent ADK pipeline and stream SSE events to client"""
        start_time = time.time()
        conv_repo = self.conversation_repo or ConversationRepository(db_session)

        # 0. Conversation Get-or-Create
        conv_id = request_dto.conversation_id
        is_first_turn = False
        conversation: Optional[Conversation] = None

        if conv_id:
            conversation = await conv_repo.get_conversation(conv_id)

        cleaned_q = " ".join(request_dto.question.strip().split())
        question_title = cleaned_q[:37] + "..." if len(cleaned_q) > 40 else cleaned_q

        if conversation is None:
            conversation = await conv_repo.create_conversation(
                user_id=request_dto.user_id,
                book_id=request_dto.book_id if not request_dto.is_global else None,
                is_global=request_dto.is_global,
                title=question_title or None,
            )
            conv_id = conversation.id
            is_first_turn = True
        elif conversation.title in [
            None,
            "",
            "يېڭى سۆھبەت",
            "New Conversation",
            "سۆھبەت",
        ]:
            await conv_repo.update_title(conv_id, question_title)

        # Fetch recent turns for pre-processing analysis context
        history_msgs = await conv_repo.get_recent_messages(conv_id, limit=6)
        history_str = format_history_for_analysis(history_msgs)
        history_dicts = [
            {"role": msg.role, "text": msg.content} for msg in history_msgs
        ]

        char_id = request_dto.character_id or DEFAULT_CHARACTER_ID
        character = CHARACTERS.get(char_id)
        persona_prompt = character.persona_prompt if character else None
        character_categories = character.categories if character else []

        book = None
        if not request_dto.is_global and request_dto.book_id:
            books_repo = BooksRepository(db_session)
            book = await books_repo.get(request_dto.book_id)

        configs_repo = SystemConfigsRepository(db_session)
        chat_model = await configs_repo.get_value("gemini_chat_model") or model_name
        agent_model = (
            await configs_repo.get_value("gemini_agent_loop_model") or chat_model
        )

        embedding_model = await configs_repo.get_value(
            "gemini_embedding_model"
        ) or getattr(settings, "gemini_embedding_model", "text-embedding-004")
        embeddings = llm_resources.get_embeddings(embedding_model)

        # 1. Build QueryContext for tool backward-compatibility & pre-processing
        ctx = QueryContext(
            question=request_dto.question,
            book_id=request_dto.book_id if not request_dto.is_global else None,
            is_global=request_dto.is_global,
            user_id=request_dto.user_id,
            current_page=request_dto.current_page,
            character_id=char_id,
            session=db_session,
            history=history_dicts,
            book=book,
            persona_prompt=persona_prompt,
            character_categories=character_categories,
            chat_history_str=history_str,
            rag_chain=llm_resources.get_rag_chain(chat_model),
            rewrite_chain=llm_resources.get_rewrite_chain(agent_model),
            embeddings=embeddings,
            start_ts=time.monotonic(),
            agent_model=agent_model,
        )
        set_current_query_context(ctx)

        # 2. Phrase-intent gate (keyword-search-rework-plan.md Phase 1):
        # A quoted / explicit-exact-phrase question checks the DB catalog first.
        # If the quoted text or question references a known book title, it is scoped
        # to that book and routed through normal RAG (vector + graph + LLM QA).
        # Unmatched quotes fall back to exact-phrase search; explicit UI flags /
        # page-finding phrasing always force exact-phrase search.
        phrase_intent = detect_phrase_intent(
            request_dto.question, exact_phrase_flag=request_dto.exact_phrase
        )

        # Enforce Reader Mode scope limit if not global; otherwise carry forward
        # the prior turn's book IDs so _build_human_message can surface them.
        if not request_dto.is_global and request_dto.book_id:
            ctx.context_book_ids = [request_dto.book_id]
        elif request_dto.is_global and request_dto.context_book_ids:
            ctx.context_book_ids = request_dto.context_book_ids

        # Catalog-first phrase resolution:
        if (
            phrase_intent.is_exact
            and not request_dto.exact_phrase
            and not phrase_intent.is_page_finding
        ):
            matched_books = await find_books_by_title_in_question(
                request_dto.question,
                db_session,
                categories=ctx.character_categories or None,
            )
            if matched_books:
                matched_book_ids = list({b["id"] for b in matched_books})
                ctx.context_book_ids = matched_book_ids
                phrase_intent.is_exact = False

        observations: list[dict] = []

        if phrase_intent.is_exact:
            yield {"type": "planning", "intent": "exact_phrase"}

            yield {
                "type": "tool_call",
                "tool": "exact_phrase_search",
                "name": "exact_phrase_search",
            }
            rag_keyword_top_k_str = await configs_repo.get_value(
                "rag_keyword_top_k", str(_EXACT_PHRASE_DEFAULT_LIMIT)
            )
            try:
                rag_keyword_top_k = int(rag_keyword_top_k_str)
            except ValueError:
                rag_keyword_top_k = _EXACT_PHRASE_DEFAULT_LIMIT

            hits, observation = await run_exact_phrase_retrieval(
                db_session,
                phrase_intent,
                book_ids=ctx.context_book_ids,
                categories=ctx.character_categories or None,
                limit=rag_keyword_top_k,
                is_global=request_dto.is_global,
            )
            observations.append(observation)
            yield {
                "type": "tool_result",
                "tool": "exact_phrase_search",
                "found": len(hits),
            }
        else:
            # 2b. Fast signal pre-processing
            try:
                signals = await analyze_query_signals(request_dto.question, ctx)
            except Exception as exc:
                log_json(
                    logger,
                    logging.WARNING,
                    "analyze_query_signals failed, proceeding without signal hints",
                    error=str(exc),
                )
                signals = {}

            intent = signals.get("intent", "open")
            yield {"type": "planning", "intent": intent}

            # 3. Retrieval Agent Execution
            retrieval_agent = build_retrieval_agent(
                model=agent_model,
                intent_signals=signals,
            )

            # Runner configuration
            if self.session_service:
                runner = Runner(
                    agent=retrieval_agent,
                    app_name="kitabim-retrieval",
                    session_service=self.session_service,
                    auto_create_session=True,
                )
                adk_session = await self.session_service.get_session(
                    app_name="kitabim-retrieval",
                    user_id=request_dto.user_id,
                    session_id=conv_id,
                )
                if adk_session is None:
                    adk_session = await self.session_service.create_session(
                        app_name="kitabim-retrieval",
                        user_id=request_dto.user_id,
                        session_id=conv_id,
                    )
            else:
                session_service = InMemorySessionService()
                adk_session = await session_service.create_session(
                    app_name="kitabim-retrieval",
                    user_id=request_dto.user_id,
                    session_id=conv_id,
                )
                runner = Runner(
                    agent=retrieval_agent,
                    app_name="kitabim-retrieval",
                    session_service=session_service,
                    auto_create_session=True,
                )

            adk_session.state["query_context"] = ctx
            adk_session.state["observations"] = []

            # AGENT_SYSTEM_PROMPT's routing rules (current book_id, current_page,
            # chat history availability, prior response book IDs) all key off an
            # explicit [Context] block in the user turn — without it the retrieval
            # agent can't tell it's in reader mode and falls back to book-discovery
            # tools it doesn't need.
            retrieval_content = types.Content(
                role="user",
                parts=[
                    types.Part.from_text(
                        text=_build_human_message(ctx, request_dto.question)
                    )
                ],
            )

            pending_calls: dict[str, str] = {}

            async for event in runner.run_async(
                user_id=request_dto.user_id,
                session_id=conv_id,
                new_message=retrieval_content,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            ):
                if not event.partial and event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.function_call:
                            call_id = (
                                getattr(part.function_call, "id", None)
                                or part.function_call.name
                            )
                            pending_calls[call_id] = part.function_call.name
                            yield {
                                "type": "tool_call",
                                "tool": part.function_call.name,
                                "name": part.function_call.name,
                            }
                        elif part.text:
                            yield {"type": "agent_thinking", "text": part.text}

                function_responses = event.get_function_responses()
                if function_responses:
                    for fr in function_responses:
                        response_data = fr.response or {}
                        call_id = getattr(fr, "id", None) or fr.name
                        tool_name = pending_calls.pop(call_id, fr.name)
                        observations.append(
                            {
                                "tool": tool_name,
                                "result": response_data,
                            }
                        )
                        found = (
                            response_data.get("found_count", 0)
                            if isinstance(response_data, dict)
                            else 0
                        )
                        yield {
                            "type": "tool_result",
                            "tool": tool_name,
                            "found": found,
                        }

        content = types.Content(
            role="user", parts=[types.Part.from_text(text=request_dto.question)]
        )

        # Page-finding exact-phrase requests are formatted as raw page hits,
        # not a synthesized answer — skip grading/reranking and the LLM
        # answer agent entirely.
        skip_answer_synthesis = phrase_intent.is_exact and phrase_intent.is_page_finding

        # 4. Context Grading
        used_book_ids = _extract_used_book_ids(observations)
        if skip_answer_synthesis:
            graded_context, before_count, after_count = "", 0, 0
        else:
            reranker_enabled = (
                await configs_repo.get_value("rag_reranker_enabled", "true")
            ).lower() == "true"
            rag_top_k_str = await configs_repo.get_value(
                "rag_vector_top_k", str(settings.rag_top_k)
            )
            try:
                rag_top_k = int(rag_top_k_str)
            except ValueError:
                rag_top_k = settings.rag_top_k

            if reranker_enabled:
                try:
                    reranker_model = await configs_repo.get_value(
                        "gemini_reranker_model", "gemini-3.1-flash-lite"
                    )
                    effective_question = _extract_effective_question(
                        request_dto.question, observations
                    )
                    graded_context, before_count, after_count = await rerank_context(
                        effective_question,
                        observations,
                        reranker_model,
                        max_chunks=rag_top_k,
                    )
                except Exception as exc:
                    log_json(
                        logger,
                        logging.WARNING,
                        "reranker failed, falling back to _grade_context",
                        error=str(exc),
                    )
                    graded_context, before_count, after_count = _grade_context(
                        observations, max_chunks=rag_top_k
                    )
            else:
                graded_context, before_count, after_count = _grade_context(
                    observations, max_chunks=rag_top_k
                )

        if before_count > 0:
            yield {"type": "grading", "before": before_count, "after": after_count}

        logger.info(
            f"[Orchestrator] Feeding graded context ({after_count} chunks out of {before_count} candidates) to Answer Agent for question: {request_dto.question!r}"
        )

        # 5. Answer Agent Execution
        yield {"type": "answer_start"}

        if skip_answer_synthesis:
            page_hits = format_page_hits(hits)
            accumulated_text = summarize_page_hits_as_text(
                hits, phrase=", ".join(phrase_intent.phrases)
            )
            yield {"type": "page_hits", "hits": page_hits, "text": accumulated_text}
        else:
            answer_agent = build_answer_agent(
                model=chat_model,
                graded_context=graded_context,
                persona_prompt=ctx.persona_prompt,
                is_global=request_dto.is_global,
                has_categories=bool(ctx.character_categories),
            )

            if self.session_service:
                answer_runner = Runner(
                    agent=answer_agent,
                    app_name="kitabim-answer",
                    session_service=self.session_service,
                    auto_create_session=True,
                )
            else:
                answer_runner = InMemoryRunner(
                    agent=answer_agent,
                    app_name="kitabim-answer",
                )

            accumulated_text = ""
            async for event in answer_runner.run_async(
                user_id=request_dto.user_id,
                session_id=conv_id,
                new_message=content,
                run_config=RunConfig(streaming_mode=StreamingMode.SSE),
            ):
                if event.partial and event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            accumulated_text += part.text
                            yield {"type": "chunk", "text": part.text}
                elif not event.partial and event.content and event.content.parts:
                    # Fallback if no partial events were emitted
                    if not accumulated_text:
                        for part in event.content.parts:
                            if part.text:
                                accumulated_text += part.text
                                yield {"type": "chunk", "text": part.text}

        yield {"type": "answer_end"}

        # 6. Safety Fix & Persistence
        fixed_text = fix_malformed_citations(accumulated_text)
        latency_ms = int((time.time() - start_time) * 1000)

        judge_scoring_enabled = (
            await configs_repo.get_value("rag_judge_scoring_enabled", "true")
        ).lower() == "true"

        eval_repo = RAGEvaluationsRepository(db_session)
        eval_record = await eval_repo.create_evaluation(
            book_id=request_dto.book_id if not request_dto.is_global else None,
            is_global=request_dto.is_global,
            question=request_dto.question,
            current_page=request_dto.current_page,
            retrieved_count=len(observations),
            context_chars=len(graded_context),
            scores=[1.0] * len(observations),
            category_filter=request_dto.context_book_ids or [],
            latency_ms=latency_ms,
            answer_chars=len(fixed_text),
            user_id=request_dto.user_id,
            agent_steps=len(observations),
            tools_called=[obs["tool"] for obs in observations],
            eval_status="queued" if judge_scoring_enabled else "skipped",
            answer=fixed_text,
            retrieved_context=graded_context,
            is_first_turn=is_first_turn,
        )
        eval_id = eval_record.id

        # Update evaluation with conversation_id link
        eval_record.conversation_id = conv_id
        await db_session.flush()
        await db_session.commit()

        if judge_scoring_enabled:
            try:
                import arq

                redis_pool = await arq.create_pool(
                    arq.connections.RedisSettings.from_dsn(settings.redis_url)
                )
                try:
                    await redis_pool.enqueue_job(
                        "rag_eval_job", eval_id=eval_id, _job_id=f"rag_eval:{eval_id}"
                    )
                finally:
                    await redis_pool.aclose()
            except Exception as exc:
                log_json(
                    logger,
                    logging.ERROR,
                    "failed to enqueue rag_eval_job",
                    eval_id=eval_id,
                    error=str(exc),
                )

        # Save turn to ConversationRepository
        await conv_repo.save_turn(
            conversation_id=conv_id,
            question=request_dto.question,
            answer=fixed_text,
            used_book_ids=used_book_ids,
            eval_id=eval_id,
            current_page=request_dto.current_page,
            agent_steps={
                "llm_calls": len(observations),
                "tools": [obs["tool"] for obs in observations],
            },
        )
        await db_session.commit()

        yield {
            "type": "done",
            "eval_id": eval_id,
            "conversation_id": conv_id,
            "used_book_ids": used_book_ids,
        }

    async def answer(
        self,
        request_dto: ChatRequestDTO,
        db_session: AsyncSession,
        model_name: str = "gemini-2.5-flash",
    ) -> dict:
        """Non-streaming convenience wrapper: drains stream_response and
        returns the concatenated answer text plus the done-event metadata."""
        answer_text = ""
        done_meta: dict = {}
        async for event in self.stream_response(request_dto, db_session, model_name):
            if isinstance(event, dict):
                if event.get("type") == "chunk":
                    answer_text += event.get("text", "")
                elif event.get("type") == "page_hits":
                    answer_text += event.get("text", "")
                elif event.get("type") == "done":
                    done_meta = event
        return {
            "answer": answer_text,
            "conversation_id": done_meta.get("conversation_id"),
            "used_book_ids": done_meta.get("used_book_ids", []),
            "eval_id": done_meta.get("eval_id"),
        }
