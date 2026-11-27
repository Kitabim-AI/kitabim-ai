"""Gemini-based Text-to-Speech service scoped strictly to Q&A answers."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from typing import AsyncIterator, Literal, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import session as db_session_mod
from app.db.models import Conversation, ConversationMessage, RAGEvaluation
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.db.repositories.tts_cache_repository import TtsCacheRepository
from app.llm.models import stream_tts_pcm
from app.llm.pricing import estimate_cost_usd, get_model_pricing_from_repo
from app.models.user import User
from app.services.cache_service import cache_service
from app.services.storage_service import storage
from app.services.tts_limit_service import tts_limit_service
from app.utils.observability import log_json
from app.utils.redis_lock import RedisLock
from app.utils.tts_text import prepare_answer_for_tts, split_tts_chunks

logger = logging.getLogger("app.tts")

TTS_SAMPLE_RATE = 24000
TTS_CHANNELS = 1
TTS_BYTES_PER_SAMPLE = 2  # 16-bit signed little-endian PCM
TTS_MP3_BITRATE = "64k"
TTS_CACHE_FORMAT_TAG = "mp3_64k_24k_mono"
# Minimum streamed PCM bytes (~10s) to still charge daily quota if client disconnects mid-stream
_MIN_QUOTA_ABORT_BYTES = TTS_SAMPLE_RATE * TTS_BYTES_PER_SAMPLE * 10
_LOCK_TIMEOUT_SECONDS = 120
_LOCK_WAIT_MAX_SECONDS = 25.0
_LOCK_WAIT_POLL_SECONDS = 0.5
_INTER_CHUNK_SILENCE_BYTES = b"\x00" * (
    TTS_SAMPLE_RATE * TTS_BYTES_PER_SAMPLE * 3 // 10
)  # 300ms silence between chunks


class TtsDisabledError(Exception):
    """Raised when tts_enabled system config is false."""


class TtsConfigError(Exception):
    """Raised when required TTS configuration (e.g., tts_gemini_model) is missing."""


class TtsNotFoundError(Exception):
    """Raised when the requested question answer does not exist or is not accessible."""


class TtsEmptyTextError(Exception):
    """Raised when the answer contains no speakable text after Markdown cleanup."""


class TtsQuotaExceededError(Exception):
    """Raised when the user has reached their daily uncached TTS generation limit."""


@dataclass(frozen=True)
class TtsRuntimeConfig:
    enabled: bool
    model: str
    voice: str
    style: str
    timeout: float
    max_chars: int


@dataclass
class TtsPreparedResponse:
    kind: Literal["cached_mp3", "stream_pcm"]
    content_hash: str
    truncated: bool
    sample_rate: int = TTS_SAMPLE_RATE
    duration_sec: Optional[float] = None
    audio_bytes: Optional[bytes] = None
    pcm_stream: Optional[AsyncIterator[bytes]] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


def compute_tts_content_hash(
    *,
    spoken_text: str,
    model: str,
    voice: str,
    style: str,
    fmt: str = TTS_CACHE_FORMAT_TAG,
) -> str:
    payload = f"v1|{model}|{voice}|{style}|{fmt}|{spoken_text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_tts_storage_path(content_hash: str) -> str:
    return f"tts/answers/{content_hash[:2]}/{content_hash}.mp3"


async def transcode_pcm_to_mp3(
    pcm_bytes: bytes,
    *,
    sample_rate: int = TTS_SAMPLE_RATE,
    bitrate: str = TTS_MP3_BITRATE,
) -> bytes:
    """Transcode raw 16-bit signed LE mono PCM bytes into MP3 via ffmpeg."""
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        str(TTS_CHANNELS),
        "-i",
        "pipe:0",
        "-codec:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        "-f",
        "mp3",
        "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate(input=pcm_bytes)
    if proc.returncode != 0 or not stdout:
        err_msg = stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"ffmpeg MP3 transcode failed (rc={proc.returncode}): {err_msg}"
        )
    return stdout


# Keep strong references to background finalization tasks until they complete
_background_tasks: set[asyncio.Task] = set()


def _track_background_task(task: asyncio.Task) -> None:
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


class TtsService:
    """Orchestrates Q&A answer resolution, caching, streaming PCM, and MP3 persistence."""

    async def get_runtime_config(self, session: AsyncSession) -> TtsRuntimeConfig:
        repo = SystemConfigsRepository(session)
        enabled_raw = await repo.get_value("tts_enabled", "true")
        enabled = str(enabled_raw or "false").strip().lower() in ("true", "1", "yes")
        if not enabled:
            raise TtsDisabledError("TTS feature is currently disabled")

        model = (await repo.get_value("tts_gemini_model") or "").strip()
        if not model:
            raise TtsConfigError("system_config 'tts_gemini_model' is not set")

        voice = (
            await repo.get_value("tts_default_voice", "Sadaltager") or "Sadaltager"
        ).strip()
        style = (
            await repo.get_value(
                "tts_default_style", "calm, clear, articulate narrator"
            )
            or ""
        ).strip()

        timeout_raw = await repo.get_value("tts_gemini_timeout", "90")
        try:
            timeout = max(10.0, float(timeout_raw or 90))
        except (ValueError, TypeError):
            timeout = 90.0

        max_chars_raw = await repo.get_value("tts_max_chars", "5000")
        try:
            max_chars = max(100, int(max_chars_raw or 5000))
        except (ValueError, TypeError):
            max_chars = 5000

        return TtsRuntimeConfig(
            enabled=True,
            model=model,
            voice=voice,
            style=style,
            timeout=timeout,
            max_chars=max_chars,
        )

    async def resolve_answer_text(
        self,
        *,
        user: User,
        session: AsyncSession,
        message_id: Optional[str] = None,
        eval_id: Optional[int] = None,
    ) -> str:
        """Look up a Q&A assistant answer from PostgreSQL and enforce ownership.

        Strictly scopes TTS to assistant answers from Global Chat and Reader Chat.
        """
        if message_id:
            stmt = (
                select(ConversationMessage, Conversation)
                .join(
                    Conversation,
                    ConversationMessage.conversation_id == Conversation.id,
                )
                .where(
                    ConversationMessage.id == message_id,
                    ConversationMessage.role == "model",
                    Conversation.user_id == user.id,
                    Conversation.deleted_at.is_(None),
                )
            )
            result = await session.execute(stmt)
            row = result.first()
            if row is not None:
                msg, _conv = row
                if msg.content and msg.content.strip():
                    return msg.content
            if not eval_id:
                raise TtsNotFoundError("Answer message not found")

        if eval_id is not None:
            eval_record = await session.get(RAGEvaluation, eval_id)
            if (
                eval_record is not None
                and eval_record.answer
                and eval_record.answer.strip()
                and (
                    eval_record.user_id == user.id or bool(eval_record.show_on_homepage)
                )
            ):
                return eval_record.answer

        raise TtsNotFoundError("Answer not found")

    async def _attach_tts_cost_to_message(
        self,
        *,
        message_id: Optional[str],
        session: AsyncSession,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
    ) -> None:
        """Persist TTS generation cost into ConversationMessage.agent_steps['tts_cost']."""
        if not message_id:
            return
        try:
            msg = await session.get(ConversationMessage, message_id)
            if msg is None or msg.role != "model":
                return
            steps = dict(msg.agent_steps) if isinstance(msg.agent_steps, dict) else {}
            new_tts_cost = {
                "input_tokens": int(input_tokens),
                "output_tokens": int(output_tokens),
                "cost_usd": round(float(cost_usd), 6),
            }
            if steps.get("tts_cost") == new_tts_cost:
                return
            steps["tts_cost"] = new_tts_cost
            msg.agent_steps = steps
            await session.commit()
        except Exception as exc:
            log_json(
                logger,
                logging.WARNING,
                "Failed to persist TTS cost on ConversationMessage",
                message_id=message_id,
                error=str(exc),
            )

    async def get_cache_lookup_config(
        self, session: AsyncSession
    ) -> Optional[TtsRuntimeConfig]:
        """Load TTS model/voice/style/max_chars for cache-only lookups (no API call)."""
        repo = SystemConfigsRepository(session)
        model = (await repo.get_value("tts_gemini_model") or "").strip()
        if not model:
            return None

        voice = (
            await repo.get_value("tts_default_voice", "Sadaltager") or "Sadaltager"
        ).strip()
        style = (
            await repo.get_value(
                "tts_default_style", "calm, clear, articulate narrator"
            )
            or ""
        ).strip()

        max_chars_raw = await repo.get_value("tts_max_chars", "5000")
        try:
            max_chars = max(100, int(max_chars_raw or 5000))
        except (ValueError, TypeError):
            max_chars = 5000

        return TtsRuntimeConfig(
            enabled=True,
            model=model,
            voice=voice,
            style=style,
            timeout=90.0,
            max_chars=max_chars,
        )

    async def find_cached_entries_for_answers(
        self,
        answers_by_id: dict[int, Optional[str]],
        session: AsyncSession,
    ) -> dict[int, object]:
        """Batch-check which RAGEvaluation answers already have cached MP3 audio ($0 cost)."""
        cfg = await self.get_cache_lookup_config(session)
        if cfg is None or not answers_by_id:
            return {}

        id_to_hash: dict[int, str] = {}
        for eval_id, raw_answer in answers_by_id.items():
            if not raw_answer or not raw_answer.strip():
                continue
            spoken_text, _ = prepare_answer_for_tts(raw_answer, max_chars=cfg.max_chars)
            if not spoken_text:
                continue
            id_to_hash[eval_id] = compute_tts_content_hash(
                spoken_text=spoken_text,
                model=cfg.model,
                voice=cfg.voice,
                style=cfg.style,
            )

        if not id_to_hash:
            return {}

        cache_repo = TtsCacheRepository(session)
        entries_by_hash = await cache_repo.get_by_hashes(list(set(id_to_hash.values())))
        return {
            eval_id: entries_by_hash[h]
            for eval_id, h in id_to_hash.items()
            if h in entries_by_hash
        }

    async def get_cached_audio_for_eval_admin(
        self, eval_id: int, session: AsyncSession
    ) -> TtsPreparedResponse:
        """Return already-cached MP3 audio for an evaluation (admin review, strictly $0 cost).

        Never invokes Gemini TTS or consumes quota. Raises TtsNotFoundError if not cached.
        """
        eval_record = await session.get(RAGEvaluation, eval_id)
        if (
            eval_record is None
            or not eval_record.answer
            or not eval_record.answer.strip()
        ):
            raise TtsNotFoundError("Answer not found")

        cfg = await self.get_cache_lookup_config(session)
        if cfg is None:
            raise TtsNotFoundError("Cached audio not found")

        spoken_text, was_truncated = prepare_answer_for_tts(
            eval_record.answer, max_chars=cfg.max_chars
        )
        if not spoken_text:
            raise TtsNotFoundError("Cached audio not found")

        content_hash = compute_tts_content_hash(
            spoken_text=spoken_text,
            model=cfg.model,
            voice=cfg.voice,
            style=cfg.style,
        )
        cached = await self._try_load_cached(
            content_hash, session, truncated=was_truncated
        )
        if cached is None:
            raise TtsNotFoundError("Cached audio not found")
        return cached

    async def get_cached_cost(
        self, content_hash: str, session: AsyncSession
    ) -> Optional[dict]:
        """Return persisted TTS cost metadata for a cached content_hash."""
        cache_repo = TtsCacheRepository(session)
        entry = await cache_repo.get_by_hash(content_hash)
        if entry is None:
            return None
        return {
            "ready": True,
            "inputTokens": int(entry.input_tokens or 0),
            "outputTokens": int(entry.output_tokens or 0),
            "costUsd": float(entry.cost_usd) if entry.cost_usd is not None else 0.0,
            "durationSec": entry.duration_sec,
        }

    async def _try_load_cached(
        self,
        content_hash: str,
        session: AsyncSession,
        *,
        truncated: bool,
        message_id: Optional[str] = None,
    ) -> Optional[TtsPreparedResponse]:
        cache_repo = TtsCacheRepository(session)
        entry = await cache_repo.get_by_hash(content_hash)
        if entry is None:
            return None

        if not storage.exists(entry.storage_path):
            log_json(
                logger,
                logging.WARNING,
                "TTS cache DB row exists but storage file missing; regenerating",
                content_hash=content_hash,
                storage_path=entry.storage_path,
            )
            return None

        audio_bytes = await storage.read_bytes(entry.storage_path)
        try:
            await cache_repo.touch_hit(content_hash)
        except Exception as exc:
            log_json(
                logger,
                logging.WARNING,
                "Failed to update TTS cache hit timestamp",
                content_hash=content_hash,
                error=str(exc),
            )

        inp_tokens = int(entry.input_tokens or 0)
        out_tokens = int(entry.output_tokens or 0)
        cost_usd = float(entry.cost_usd) if entry.cost_usd is not None else 0.0

        await self._attach_tts_cost_to_message(
            message_id=message_id,
            session=session,
            input_tokens=inp_tokens,
            output_tokens=out_tokens,
            cost_usd=cost_usd,
        )

        log_json(
            logger,
            logging.INFO,
            "TTS cache hit",
            content_hash=content_hash,
            size_bytes=len(audio_bytes),
            duration_sec=entry.duration_sec,
        )
        return TtsPreparedResponse(
            kind="cached_mp3",
            content_hash=content_hash,
            truncated=truncated,
            duration_sec=entry.duration_sec,
            audio_bytes=audio_bytes,
            input_tokens=inp_tokens,
            output_tokens=out_tokens,
            cost_usd=cost_usd,
        )

    async def prepare_answer_tts(
        self,
        *,
        user: User,
        session: AsyncSession,
        message_id: Optional[str] = None,
        eval_id: Optional[int] = None,
    ) -> TtsPreparedResponse:
        if not settings.gemini_api_key:
            raise TtsConfigError("Gemini API key not configured")

        cfg = await self.get_runtime_config(session)
        raw_answer = await self.resolve_answer_text(
            user=user,
            session=session,
            message_id=message_id,
            eval_id=eval_id,
        )
        spoken_text, was_truncated = prepare_answer_for_tts(
            raw_answer, max_chars=cfg.max_chars
        )
        if not spoken_text:
            raise TtsEmptyTextError("No speakable text in answer")

        content_hash = compute_tts_content_hash(
            spoken_text=spoken_text,
            model=cfg.model,
            voice=cfg.voice,
            style=cfg.style,
        )

        # 1. Fast path: cache hit (free & unlimited)
        cached = await self._try_load_cached(
            content_hash, session, truncated=was_truncated, message_id=message_id
        )
        if cached is not None:
            return cached

        # 2. Acquire Redis lock to coalesce concurrent misses on the same answer
        lock: Optional[RedisLock] = None
        redis_client = None
        try:
            redis_client = await cache_service.get_client()
        except Exception:
            redis_client = None

        if redis_client is not None:
            candidate_lock = RedisLock(
                redis_client,
                content_hash,
                timeout=_LOCK_TIMEOUT_SECONDS,
                prefix="tts_gen",
            )
            if await candidate_lock.acquire():
                lock = candidate_lock
            else:
                # Another request is actively synthesizing this exact hash — wait for cache
                waited = 0.0
                while waited < _LOCK_WAIT_MAX_SECONDS:
                    await asyncio.sleep(_LOCK_WAIT_POLL_SECONDS)
                    waited += _LOCK_WAIT_POLL_SECONDS
                    session.expire_all()
                    cached = await self._try_load_cached(
                        content_hash,
                        session,
                        truncated=was_truncated,
                        message_id=message_id,
                    )
                    if cached is not None:
                        return cached
                    if await candidate_lock.acquire():
                        lock = candidate_lock
                        break

        # Re-check cache once lock is held (in case prior holder just finished)
        cached = await self._try_load_cached(
            content_hash, session, truncated=was_truncated, message_id=message_id
        )
        if cached is not None:
            if lock is not None:
                await lock.release()
            return cached

        # 3. Check user daily TTS quota (only for uncached synthesis)
        usage_status = await tts_limit_service.get_user_usage_status(user, session)
        if usage_status["has_reached_limit"]:
            if lock is not None:
                await lock.release()
            log_json(
                logger,
                logging.WARNING,
                "Daily TTS limit reached",
                user_id=user.id,
                role=getattr(user.role, "value", str(user.role)),
                usage=usage_status["usage"],
                limit=usage_status["limit"],
            )
            raise TtsQuotaExceededError("Daily TTS limit reached")

        # 4. Prepare streaming PCM generator with background MP3 transcode + cache
        chunks = split_tts_chunks(spoken_text, max_chunk_chars=2500)

        async def _pcm_generator() -> AsyncIterator[bytes]:
            pcm_buf = bytearray()
            usage_out: dict[str, int] = {"input_tokens": 0, "output_tokens": 0}
            completed = False
            lock_handed_off = False
            try:
                for idx, chunk_text in enumerate(chunks):
                    if idx > 0 and pcm_buf:
                        pcm_buf.extend(_INTER_CHUNK_SILENCE_BYTES)
                        yield _INTER_CHUNK_SILENCE_BYTES
                    async for raw_pcm in stream_tts_pcm(
                        chunk_text,
                        model_name=cfg.model,
                        voice=cfg.voice,
                        style=cfg.style,
                        sample_rate=TTS_SAMPLE_RATE,
                        timeout=cfg.timeout,
                        usage_out=usage_out,
                    ):
                        pcm_buf.extend(raw_pcm)
                        yield raw_pcm
                completed = len(pcm_buf) > 0
            finally:
                if completed:
                    lock_handed_off = True
                    task = asyncio.create_task(
                        self._finalize_and_cache(
                            user=user,
                            message_id=message_id,
                            content_hash=content_hash,
                            pcm_bytes=bytes(pcm_buf),
                            cfg=cfg,
                            text_chars=len(spoken_text),
                            usage_out=usage_out,
                            lock=lock,
                        )
                    )
                    _track_background_task(task)
                else:
                    # Client disconnected or error mid-stream: do NOT cache truncated audio.
                    # Still charge quota if substantial audio (>=10s) was already delivered.
                    if len(pcm_buf) >= _MIN_QUOTA_ABORT_BYTES:
                        task = asyncio.create_task(
                            self._charge_aborted_usage(user=user)
                        )
                        _track_background_task(task)
                    if lock is not None and not lock_handed_off:
                        await lock.release()

        return TtsPreparedResponse(
            kind="stream_pcm",
            content_hash=content_hash,
            truncated=was_truncated,
            sample_rate=TTS_SAMPLE_RATE,
            pcm_stream=_pcm_generator(),
        )

    async def _charge_aborted_usage(self, *, user: User) -> None:
        try:
            async with db_session_mod.async_session_factory() as bg_session:
                await tts_limit_service.increment_usage(user, bg_session)
        except Exception as exc:
            log_json(
                logger,
                logging.WARNING,
                "Failed to charge aborted TTS usage",
                user_id=user.id,
                error=str(exc),
            )

    async def _finalize_and_cache(
        self,
        *,
        user: User,
        message_id: Optional[str],
        content_hash: str,
        pcm_bytes: bytes,
        cfg: TtsRuntimeConfig,
        text_chars: int,
        usage_out: dict[str, int],
        lock: Optional[RedisLock],
    ) -> None:
        try:
            duration_sec = round(
                len(pcm_bytes) / float(TTS_SAMPLE_RATE * TTS_BYTES_PER_SAMPLE), 2
            )
            async with db_session_mod.async_session_factory() as bg_session:
                # 1. Charge daily quota for the newly synthesized answer
                await tts_limit_service.increment_usage(user, bg_session)

                # 2. Transcode PCM -> 64 kbps MP3 via ffmpeg
                mp3_bytes = await transcode_pcm_to_mp3(
                    pcm_bytes, sample_rate=TTS_SAMPLE_RATE
                )

                # 3. Persist to configured StorageProvider (GCS or local ./data)
                storage_path = build_tts_storage_path(content_hash)
                await storage.upload_bytes(mp3_bytes, storage_path)

                # 4. Estimate USD cost & persist metadata row
                input_tokens = int(usage_out.get("input_tokens") or 0)
                output_tokens = int(usage_out.get("output_tokens") or 0)
                if output_tokens <= 0 and duration_sec > 0:
                    # Gemini TTS bills 25 output tokens per second of audio
                    output_tokens = max(1, int(round(duration_sec * 25)))

                config_repo = SystemConfigsRepository(bg_session)
                pricing_map, fallback_price = await get_model_pricing_from_repo(
                    config_repo
                )
                cost_usd = estimate_cost_usd(
                    cfg.model,
                    input_tokens,
                    output_tokens,
                    pricing_map=pricing_map,
                    fallback_price=fallback_price,
                )

                cache_repo = TtsCacheRepository(bg_session)
                await cache_repo.upsert_entry(
                    content_hash=content_hash,
                    storage_path=storage_path,
                    mime_type="audio/mpeg",
                    model=cfg.model,
                    voice=cfg.voice,
                    style=cfg.style,
                    text_chars=text_chars,
                    duration_sec=duration_sec,
                    size_bytes=len(mp3_bytes),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                )

                await self._attach_tts_cost_to_message(
                    message_id=message_id,
                    session=bg_session,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                )

                log_json(
                    logger,
                    logging.INFO,
                    "TTS audio transcoded and cached",
                    content_hash=content_hash,
                    model=cfg.model,
                    voice=cfg.voice,
                    duration_sec=duration_sec,
                    mp3_bytes=len(mp3_bytes),
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=round(cost_usd, 6),
                )
        except Exception as exc:
            log_json(
                logger,
                logging.ERROR,
                "Failed to finalize/cache TTS audio",
                content_hash=content_hash,
                error=str(exc),
            )
        finally:
            if lock is not None:
                await lock.release()


tts_service = TtsService()
