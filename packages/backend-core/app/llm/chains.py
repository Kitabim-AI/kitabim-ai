from __future__ import annotations

import logging
from typing import Any, AsyncIterator
from pydantic import BaseModel

from app.core.providers import get_llm_provider
from app.llm.models import _get_genai_client

_logger = logging.getLogger("app.llm.chains")


class TextChain:
    def __init__(
        self,
        template: str,
        model_name: str,
        run_name: str | None = None,
        partials: dict | None = None,
    ):
        self.template = template
        self.model_name = model_name
        self.run_name = run_name
        self.partials = partials or {}
        self.llm = get_llm_provider(model_name)

    async def ainvoke(self, input: dict[str, Any], **kwargs: Any) -> str:
        # Merge input with partials
        params = {**self.partials, **input}
        # Format the template using the variables
        formatted = self.template.format(**params)
        # Call the LLM
        return await self.llm.ainvoke(formatted, **kwargs)

    async def astream(self, input: dict[str, Any], **kwargs: Any) -> AsyncIterator[str]:
        # Merge input with partials
        params = {**self.partials, **input}
        # Format the template using the variables
        formatted = self.template.format(**params)
        # Stream from the LLM
        async for chunk in self.llm.astream(formatted, **kwargs):
            yield chunk


class StructuredChain:
    def __init__(
        self,
        template: str,
        model_name: str,
        response_schema: type[BaseModel],
        run_name: str | None = None,
    ):
        self.template = template
        self.model_name = model_name
        self.response_schema = response_schema
        self.run_name = run_name

    async def ainvoke(self, input: dict[str, Any], **kwargs: Any) -> BaseModel:
        client = _get_genai_client()
        model = (
            self.model_name.replace("models/", "", 1)
            if self.model_name.startswith("models/")
            else self.model_name
        )

        # If the template has format_instructions, we pass an empty string since SDK handles schema formatting natively
        params = {**input, "format_instructions": ""}
        formatted = self.template.format(**params)

        from google.genai import types

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=self.response_schema,
            temperature=0.0,
        )

        from app.llm.models import _TEXT_BREAKER, _call_with_breaker

        async def _call():
            response = await client.aio.models.generate_content(
                model=model, contents=formatted, config=config, **kwargs
            )
            return response.text or ""

        raw_response = await _call_with_breaker(_TEXT_BREAKER, _call)
        if not raw_response:
            raise ValueError(
                f"Empty LLM response for schema {self.response_schema.__name__}"
            )
        return self.response_schema.model_validate_json(raw_response)


def build_text_chain(
    template: str,
    model_name: str,
    run_name: str | None = None,
    partials: dict | None = None,
) -> TextChain:
    return TextChain(template, model_name, run_name=run_name, partials=partials)


def build_structured_chain(
    template: str,
    model_name: str,
    parser: Any,
    run_name: str | None = None,
) -> StructuredChain:
    # Extract the Pydantic schema class from output parser if passed
    if hasattr(parser, "pydantic_object"):
        schema = parser.pydantic_object
    elif hasattr(parser, "schema"):
        schema = parser.schema
    else:
        schema = parser
    return StructuredChain(
        template, model_name, response_schema=schema, run_name=run_name
    )
