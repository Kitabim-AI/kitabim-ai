"""Agent loop configuration constants — single source of truth for numeric limits."""

AGENT_MAX_STEPS = 4          # maximum ReAct loop iterations
AGENT_ENOUGH_CHUNKS = 8      # early-exit threshold: stop once this many chunks are collected
AGENT_MAX_CONTEXT_CHUNKS = 15  # hard cap on chunks passed to the answer LLM
