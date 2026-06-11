"""Agentic RAG — LLM-driven retrieval loop replacing the fixed StandardRAGHandler pipeline."""
from .adk_agent import build_rag_agent
import os

# Expose root_agent directly in the agent package so it conforms to the ADK AgentEvaluator
# module naming convention (which requires the module name to end with '.agent' and expose 'root_agent').
_model = os.environ.get("AGENT_MODEL", "gemini-2.5-flash")
root_agent = build_rag_agent(_model)
