import logging
from google import genai
from app.core.config import settings
from app.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerOpen
from app.utils.observability import log_json

_CLIENT = None
_TEXT_BREAKER = CircuitBreaker(
    "llm_generate",
    CircuitBreakerConfig(
        failure_threshold=settings.llm_cb_failure_threshold,
        recovery_timeout=float(settings.llm_cb_recovery_seconds),
        half_open_max_calls=settings.llm_cb_half_open_max_calls,
    ),
)
_EMBED_BREAKER = CircuitBreaker(
    "llm_embed",
    CircuitBreakerConfig(
        failure_threshold=settings.llm_cb_failure_threshold,
        recovery_timeout=float(settings.llm_cb_recovery_seconds),
        half_open_max_calls=settings.llm_cb_half_open_max_calls,
    ),
)
_logger = logging.getLogger("app.genai")


def get_genai_client():
    global _CLIENT
    if _CLIENT is None:
        if settings.gemini_api_key:
            _CLIENT = genai.Client(api_key=settings.gemini_api_key)
        else:
            _CLIENT = genai.Client()
    return _CLIENT


async def generate_content(**kwargs):
    client = get_genai_client()

    async def _call():
        return await client.aio.models.generate_content(**kwargs)

    try:
        return await _TEXT_BREAKER.call(_call)
    except CircuitBreakerOpen as exc:
        log_json(_logger, logging.ERROR, "LLM generate circuit open", error=str(exc))
        raise


async def embed_content(**kwargs):
    client = get_genai_client()

    async def _call():
        return await client.aio.models.embed_content(**kwargs)

    try:
        return await _EMBED_BREAKER.call(_call)
    except CircuitBreakerOpen as exc:
        log_json(_logger, logging.ERROR, "LLM embed circuit open", error=str(exc))
        raise


def extract_embedding_vector(result):
    embeddings = getattr(result, "embeddings", None)
    if embeddings:
        first = embeddings[0]
        values = getattr(first, "values", None)
        if values is not None:
            return values
        if isinstance(first, dict):
            if "values" in first:
                return first["values"]
            if "embedding" in first:
                return first["embedding"]

    if isinstance(result, dict):
        if "embedding" in result:
            return result["embedding"]
        if "embeddings" in result and result["embeddings"]:
            first = result["embeddings"][0]
            if isinstance(first, dict):
                return first.get("values") or first.get("embedding") or first
    return None


def extract_embeddings_list(result):
    embeddings = getattr(result, "embeddings", None)
    if embeddings:
        vectors = []
        for emb in embeddings:
            values = getattr(emb, "values", None)
            if values is not None:
                vectors.append(values)
            elif isinstance(emb, dict):
                vectors.append(emb.get("values") or emb.get("embedding") or emb)
            else:
                vectors.append(emb)
        return vectors

    if isinstance(result, dict):
        if "embedding" in result:
            return [result["embedding"]]
        if "embeddings" in result:
            vectors = []
            for emb in result["embeddings"]:
                if isinstance(emb, dict):
                    vectors.append(emb.get("values") or emb.get("embedding") or emb)
                else:
                    vectors.append(emb)
            return vectors
    return []
