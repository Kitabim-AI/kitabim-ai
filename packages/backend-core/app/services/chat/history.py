"""Helper utilities for formatting conversation message history"""

from __future__ import annotations

from typing import List
from app.db.models import ConversationMessage


def format_history_for_analysis(messages: List[ConversationMessage]) -> str:
    """Format recent turns into a text block for pre-processing analysis"""
    if not messages:
        return ""

    formatted_turns = []
    for msg in messages:
        role_label = "User" if msg.role == "user" else "Assistant"
        formatted_turns.append(f"{role_label}: {msg.content}")

    return "\n".join(formatted_turns)
