from __future__ import annotations

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.langchain.models import build_text_llm


def build_text_chain(
    template: str,
    model_name: str,
    run_name: str | None = None,
    partials: dict | None = None,
):
    prompt = ChatPromptTemplate.from_template(template)
    if partials:
        prompt = prompt.partial(**partials)
    llm = build_text_llm(model_name)
    chain = prompt | llm | StrOutputParser()
    if run_name:
        return chain.with_config(run_name=run_name)
    return chain


def build_structured_chain(
    template: str,
    model_name: str,
    parser,
    run_name: str | None = None,
):
    prompt = ChatPromptTemplate.from_template(template).partial(
        format_instructions=parser.get_format_instructions()
    )
    llm = build_text_llm(model_name)
    chain = prompt | llm | StrOutputParser() | parser
    if run_name:
        return chain.with_config(run_name=run_name)
    return chain
