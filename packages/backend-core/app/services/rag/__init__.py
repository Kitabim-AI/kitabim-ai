"""RAG package — public exports."""
from app.services.rag.context import QueryContext
from app.services.rag.base_handler import QueryHandler
from app.services.rag.registry import HandlerRegistry, get_registry
from app.services.rag.llm_resources import CategoryResponse  # re-export for compat

__all__ = [
    "QueryContext",
    "QueryHandler",
    "HandlerRegistry",
    "get_registry",
    "CategoryResponse",
]
