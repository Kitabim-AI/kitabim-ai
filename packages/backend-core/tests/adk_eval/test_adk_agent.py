import os
import re
import pytest
import glob
from unittest.mock import patch
from google.adk.evaluation.agent_evaluator import AgentEvaluator
from google.adk.evaluation.base_eval_service import InferenceConfig

# Force sequential execution to prevent Gemini API rate limiting
InferenceConfig.model_fields["parallelism"].default = 1


# Custom ROUGE tokenizer that supports Uyghur/Arabic script characters
def custom_tokenize(text: str, stemmer=None) -> list[str]:
    text = text.lower()
    tokens = text.split()
    cleaned_tokens = []
    for token in tokens:
        # Keep alphanumeric characters and Uyghur/Arabic Unicode range letters
        cleaned = re.sub(r"^[^\w\u0600-\u06FF]+|[^\w\u0600-\u06FF]+$", "", token)
        if cleaned:
            cleaned_tokens.append(cleaned)
    return cleaned_tokens


# Mock tool dispatcher to decouple ADK agent reasoning from live database/graph resources during unit/regression tests.
async def mock_dispatch_tool_with_retry(tool_name: str, tool_args: dict, ctx) -> dict:
    if tool_name == "find_books_by_title":
        question = tool_args.get("question", "")
        if "ئانا يۇرت" in question:
            return {
                "ok": True,
                "book_ids": ["book-ana-yurt"],
                "books": [
                    {
                        "id": "book-ana-yurt",
                        "title": "ئانا يۇرت",
                        "author": "زوردۇن سابىر",
                        "volume": 1,
                    }
                ],
                "found_count": 1,
            }
        elif "باھادىرنامە" in question:
            return {
                "ok": True,
                "book_ids": ["book-bahadirname"],
                "books": [
                    {
                        "id": "book-bahadirname",
                        "title": "باھادىرنامە",
                        "author": "ياسىنجان سادىق چوغلان",
                        "volume": 1,
                    }
                ],
                "found_count": 1,
            }
        return {
            "ok": True,
            "book_ids": ["book-123"],
            "books": [
                {
                    "id": "book-123",
                    "title": "لېيىغان بۇلاق",
                    "author": "جالالىدىن بەھرام",
                    "volume": 1,
                }
            ],
            "found_count": 1,
        }
    elif tool_name == "get_book_author":
        question = tool_args.get("question", "")
        if "ئانا يۇرت" in question:
            return {
                "ok": True,
                "author": "زوردۇن سابىر",
                "title": "ئانا يۇرت",
                "context": "«ئانا يۇرت» كىتابىنى زوردۇن سابىر يازغان.",
                "found_count": 1,
            }
        elif "باھادىرنامە" in question:
            return {
                "ok": True,
                "author": "ياسىنجان سادىق چوغلان",
                "title": "باھادىرنامە",
                "context": "«باھادىرنامە» كىتابىنى ياسىنجان سادىق چوغلان يازغان.",
                "found_count": 1,
            }
        return {"ok": True, "author": "جالالىدىن بەھرام", "found_count": 1}
    elif tool_name == "get_books_by_author":
        question = tool_args.get("question", "")
        if "زوردۇن" in question or "سابىر" in question:
            return {
                "ok": True,
                "author": "زوردۇن سابىر",
                "books": [
                    {
                        "id": "book-ana-yurt",
                        "title": "ئانا يۇرت",
                    }
                ],
                "found_count": 1,
            }
        return {"ok": True, "books": [], "found_count": 0}
    elif tool_name == "search_catalog":
        return {
            "ok": True,
            "context": "كۇتۇبخانىدا بىر قىسىم كىتابلار بار، مەسىلەن «لېيىغان بۇلاق»، «ئانا يۇرت» ۋە «باھادىرنامە».",
            "book_count": 3,
        }
    elif tool_name == "search_chunks":
        query = tool_args.get("query", "")
        if "ئانا يۇرت" in query or "زوردۇن" in query:
            return {
                "ok": True,
                "chunks": [
                    {
                        "text": "بۇ كىتابنىڭ ئاپتورى زوردۇن سابىر.",
                        "score": 0.9,
                        "book_id": "book-ana-yurt",
                        "page": 1,
                    }
                ],
                "found_count": 1,
            }
        elif "باھادىرنامە" in query or "ياسىنجان" in query:
            return {
                "ok": True,
                "chunks": [
                    {
                        "text": "بۇ كىتابنىڭ ئاپتورى ياسىنجان سادىق چوغلان.",
                        "score": 0.9,
                        "book_id": "book-bahadirname",
                        "page": 1,
                    }
                ],
                "found_count": 1,
            }
        return {
            "ok": True,
            "chunks": [
                {
                    "text": "بۇ كىتابنىڭ ئاپتورى جالالىدىن بەھرام.",
                    "score": 0.9,
                    "book_id": "book-123",
                    "page": 1,
                }
            ],
            "found_count": 1,
        }
    elif tool_name == "lookup_uyghur_word":
        word = tool_args.get("word", "")
        return {
            "ok": True,
            "entries": [
                {"word": word, "definition": f"{word} - دوستلۇق، سۆيگۈ، ئىشق-مۇھەببەت."}
            ],
            "found_count": 1,
        }
    elif tool_name == "lookup_history_term":
        term = tool_args.get("term", "")
        return {
            "ok": True,
            "definition": f"{term} - موغۇلىستاننىڭ خاقانى، چىڭگىزخان سۇلالىسىدىن بولغان تارىخىي شەخس.",
            "found_count": 1,
        }
    elif tool_name == "lookup_uyghur_name":
        name = tool_args.get("name", "")
        return {
            "ok": True,
            "meaning": f"{name} دېگەن ئىسىم بىلىملىك، ئوقۇمۇشلۇق دېگەن مەنىدە.",
            "found_count": 1,
        }
    elif tool_name == "lookup_proverbs":
        keyword = tool_args.get("keyword", "")
        return {
            "ok": True,
            "proverbs": [{"text": f"{keyword} كۈچتۇر."}],
            "found_count": 1,
        }
    elif tool_name == "rewrite_query":
        query = tool_args.get("query", "")
        return {
            "ok": True,
            "rewritten_query": "زوردۇن سابىرنىڭ كىتابلىرى قايسىلار؟",
        }
    elif tool_name == "get_current_page":
        return {
            "ok": True,
            "content": "بۇ بەتتە ئۇيغۇر تارىخى ۋە مەدەنىيىتى ھەققىدە قىسقىچە بايان قىلىنغان.",
            "page": 12,
            "book_title": "ئانا يۇرت",
        }
    return {"ok": True, "data": {}, "found_count": 0}


current_dir = os.path.dirname(os.path.abspath(__file__))
cases_dir = os.path.join(current_dir, "cases")
eval_files = sorted(glob.glob(os.path.join(cases_dir, "*.test.json")))


@pytest.mark.asyncio
@pytest.mark.parametrize("eval_dataset_file", eval_files)
async def test_adk_agent_evaluation(eval_dataset_file):
    from google.adk.evaluation.evaluation_generator import EvaluationGenerator
    from google.adk.evaluation.base_eval_service import InferenceConfig
    import asyncio

    # Force sequential execution (parallelism = 1) to prevent Gemini API rate limiting
    InferenceConfig.model_fields["parallelism"].default = 1

    original_generate = EvaluationGenerator._generate_inferences_from_root_agent

    async def sleep_then_generate(*args, **kwargs):
        # Sleep for 4.0 seconds before running each case to prevent Gemini API rate limiting
        await asyncio.sleep(4.0)
        return await original_generate(*args, **kwargs)

    # Patch the dispatching, the tokenizer, and generator so we execute cleanly in Uyghur.
    with patch(
        "app.services.rag.agent.tools._dispatch_tool_with_retry",
        side_effect=mock_dispatch_tool_with_retry,
    ), patch(
        "rouge_score.tokenize.tokenize",
        side_effect=custom_tokenize,
    ), patch(
        "google.adk.evaluation.evaluation_generator.EvaluationGenerator._generate_inferences_from_root_agent",
        side_effect=sleep_then_generate,
    ):
        await AgentEvaluator.evaluate(
            agent_module="app.services.rag.agent",
            eval_dataset_file_path_or_dir=eval_dataset_file,
            num_runs=1,
            print_detailed_results=True,
        )
