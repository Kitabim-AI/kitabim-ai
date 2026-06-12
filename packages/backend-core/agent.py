"""ADK web entry point — exposes `root_agent` for `adk web` discovery.

Run from the packages/backend-core directory:
    adk web

Or from the repo root:
    adk web packages/backend-core
"""

from app.services.rag.agent.adk_agent import build_rag_agent

# Default model for local ADK web dev session.
# Override by setting AGENT_MODEL env var before running `adk web`.
import os

_model = os.environ.get("AGENT_MODEL", "gemini-2.5-flash")

root_agent = build_rag_agent(_model)
