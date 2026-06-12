# Google ADK RAG Evaluation Guide

This guide describes how to configure, execute, and extend automated RAG evaluations for Kitabim.AI using the Google Agent Development Kit (ADK) evaluation framework.

---

## 🏗️ Evaluation Architecture

The evaluation setup uses Google ADK's `AgentEvaluator` combined with `pytest` to verify the agent's reasoning loop, planning logic, and tool routing without requiring a live database or graph connection.

### Core Components
1. **Agent Module (`app.services.rag.agent`)**: The target Python package containing the ADK agent. We expose `root_agent` inside `app/services/rag/agent/__init__.py` to make it discoverable by `AgentEvaluator`.
2. **Evaluation Dataset (`adk_evalset.test.json`)**: Formatted in ADK's `EvalSet` schema, containing test cases with input queries, expected tool call sequences, and reference outputs.
3. **Evaluation Configuration (`test_config.json`)**: Configures metrics and thresholds (e.g., asserting that the tool trajectory match score is `1.0`).
4. **Pytest Harness (`test_adk_agent.py`)**: Executes `AgentEvaluator.evaluate()` and intercepts the underlying tool runner using a mocked tool dispatcher (`_dispatch_tool_with_retry`) to ensure fast and deterministic execution.

---

## 📈 Evaluation Metrics

The default configuration evaluates:

| Metric Name | Description | Threshold |
|---|---|---|
| `tool_trajectory_avg_score` | Asserts that the agent invoked the correct sequence of tools. | `1.0` (Exact Match) |
| `response_match_score` | Measures text overlap/similarity of the final response to a golden reference. | `0.5` |

---

## 🚀 How to Run Evaluations

Since our code runs inside a Docker Compose environment, all evaluation dependencies and tests run inside the `backend` service.

### 1. From the Host Command Line (Recommended)
You can use the custom runner script in the `scripts/` directory:
```bash
python3 scripts/run_adk_evaluation.py
```

### 2. Directly inside the Backend Container
Alternatively, run pytest inside the container:
```bash
docker compose exec backend pytest packages/backend-core/tests/adk_eval -v -s
```

---

## ✍️ Adding New Test Cases

To add a new query evaluation case, open `packages/backend-core/tests/adk_eval/adk_evalset.test.json` and append an entry to the JSON list:

```json
{
  "name": "test_my_new_case",
  "data": [
    {
      "query": "Who is the author of X?",
      "expected_tool_use": [
        {
          "tool_name": "find_books_by_title",
          "tool_input": {
            "question": "Who is the author of X?"
          }
        },
        {
          "tool_name": "get_book_author",
          "tool_input": {
            "question": "Who is the author of X?"
          }
        }
      ],
      "expected_intermediate_agent_responses": [],
      "reference": "The author of book X is Y."
    }
  ],
  "initial_session": {
    "state": {
      "query_context": {
        "is_global": true,
        "book_id": "global",
        "user_id": "test-eval-user",
        "history": [],
        "agent_model": "gemini-2.0-flash-001"
      },
      "observations": []
    },
    "app_name": "kitabim",
    "user_id": "test-eval-user"
  }
}
```

If the new test case calls a new tool or returns a different mock value, update the mock dispatcher implementation inside `packages/backend-core/tests/adk_eval/test_adk_agent.py` to return the appropriate response.
