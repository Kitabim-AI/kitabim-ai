import os
import pytest
from unittest.mock import patch
from google.adk.evaluation.agent_evaluator import AgentEvaluator

# Mock tool dispatcher to decouple ADK agent reasoning from live database/graph resources during unit/regression tests.
async def mock_dispatch_tool_with_retry(tool_name: str, tool_args: dict, ctx) -> dict:
    if tool_name == "find_books_by_title":
        question = tool_args.get("question", "")
        if "ئانا يۇرت" in question:
            return {
                "ok": True,
                "book_ids": ["book-ana-yurt"],
                "books": [{"id": "book-ana-yurt", "title": "ئانا يۇرت", "author": "زوردۇن سابىر", "volume": 1}],
                "found_count": 1
            }
        elif "باھادىرنامە" in question:
            return {
                "ok": True,
                "book_ids": ["book-bahadirname"],
                "books": [{"id": "book-bahadirname", "title": "باھادىرنامە", "author": "ياسىنجان سادىق چوغلان", "volume": 1}],
                "found_count": 1
            }
        return {
            "ok": True,
            "book_ids": ["book-123"],
            "books": [{"id": "book-123", "title": "لېيىغان بۇلاق", "author": "جالالىدىن بەھرام", "volume": 1}],
            "found_count": 1
        }
    elif tool_name == "get_book_author":
        question = tool_args.get("question", "")
        if "ئانا يۇرت" in question:
            return {
                "ok": True,
                "author": "زوردۇن سابىر",
                "title": "ئانا يۇرت",
                "context": "The book 'ئانا يۇرت' was written by زوردۇن سابىر.",
                "found_count": 1
            }
        elif "باھادىرنامە" in question:
            return {
                "ok": True,
                "author": "ياسىنجان سادىق چوغلان",
                "title": "باھادىرنامە",
                "context": "The book 'باھادىرنامە' was written by ياسىنجان سادىق چوغلان.",
                "found_count": 1
            }
        return {
            "ok": True,
            "author": "جالالىدىن بەھرام",
            "found_count": 1
        }
    elif tool_name == "search_catalog":
        return {
            "ok": True,
            "context": "كۇتۇبخانىدا بىر قىسىم كىتابلار بار، مەسىلەن «لېيىغان بۇلاق»، «ئانا يۇرت» ۋە «باھادىرنامە».",
            "book_count": 3
        }
    elif tool_name == "search_chunks":
        query = tool_args.get("query", "")
        if "ئانا يۇرت" in query or "زوردۇن" in query:
            return {
                "ok": True,
                "chunks": [{"text": "بۇ كىتابنىڭ ئاپتورى زوردۇن سابىر.", "score": 0.9, "book_id": "book-ana-yurt", "page": 1}],
                "found_count": 1
            }
        elif "باھادىرنامە" in query or "ياسىنجان" in query:
            return {
                "ok": True,
                "chunks": [{"text": "بۇ كىتابنىڭ ئاپتورى ياسىنجان سادىق چوغلان.", "score": 0.9, "book_id": "book-bahadirname", "page": 1}],
                "found_count": 1
            }
        return {
            "ok": True,
            "chunks": [{"text": "بۇ كىتابنىڭ ئاپتورى جالالىدىن بەھرام.", "score": 0.9, "book_id": "book-123", "page": 1}],
            "found_count": 1
        }
    return {"ok": True, "data": {}, "found_count": 0}

@pytest.mark.asyncio
async def test_adk_agent_evaluation():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    eval_dataset_file = os.path.join(current_dir, "adk_evalset.test.json")
    
    # Patch the dispatching so we execute tools cleanly and deterministically.
    with patch("app.services.rag.agent.tools._dispatch_tool_with_retry", side_effect=mock_dispatch_tool_with_retry):
        await AgentEvaluator.evaluate(
            agent_module="app.services.rag.agent",
            eval_dataset_file_path_or_dir=eval_dataset_file,
            print_detailed_results=True
        )
