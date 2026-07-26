"""Answer Agent builder using Google ADK"""

from __future__ import annotations

from typing import Optional
from google.adk import Agent
from app.services.chat.answer_prompts import build_answer_instructions


def build_answer_agent(
    model: str,
    graded_context: str,
    persona_prompt: Optional[str] = None,
    is_global: bool = False,
    has_categories: bool = False,
    strict_no_answer: bool = False,
) -> Agent:
    """Build the Answer Agent for synthesizing answers from graded observations."""
    base_instructions = build_answer_instructions(
        strict_no_answer=strict_no_answer,
        suppress_page_notice=False,
        persona_prompt=persona_prompt,
        is_global=is_global,
        has_categories=has_categories,
    )

    full_instructions = (
        f"{base_instructions}\n\nRetrieved Library Context:\n{graded_context}"
    )

    agent = Agent(
        model=model,
        name="KitabimAnswerAgent",
        description="Synthesizes final Uyghur response from retrieved library context.",
        instruction=full_instructions,
        tools=[],  # Pure synthesis stage, no tools needed
    )
    return agent
