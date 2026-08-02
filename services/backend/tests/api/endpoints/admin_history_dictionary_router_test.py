import sys
import importlib.util
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[3]
BACKEND_CORE_DIR = Path(__file__).resolve().parents[5] / "packages" / "backend-core"

# Load admin_history_dictionary_router module directly
module_path = BACKEND_DIR / "api" / "endpoints" / "admin_history_dictionary_router.py"
spec = importlib.util.spec_from_file_location(
    "admin_history_dictionary_router", module_path
)
router_module = importlib.util.module_from_spec(spec)


def load_router():
    for p in [str(BACKEND_CORE_DIR), str(BACKEND_DIR)]:
        if p not in sys.path:
            sys.path.insert(0, p)
    spec.loader.exec_module(router_module)
    return router_module


@pytest.mark.asyncio
async def test_trigger_history_extraction():
    mod = load_router()
    with patch.object(mod, "enqueue_task", return_value="job-123"):
        req = mod.ExtractHistoryRequest(min_significance=5)
        res = await mod.trigger_history_extraction(
            book_id="book-123", req=req, current_admin=None
        )
        assert res["status"] == "queued"
        assert res["jobId"] == "job-123"


@pytest.mark.asyncio
async def test_list_staging_terms():
    mod = load_router()
    mock_db = AsyncMock()
    with patch.object(mod, "DictionaryRepository") as mock_repo_cls:
        mock_repo = AsyncMock()
        mock_repo.get_staging_terms.return_value = {
            "items": [
                {"id": 1, "term": "سۇلتان سۇتۇق بۇغراخان", "significanceScore": 9}
            ],
            "total": 1,
            "page": 1,
            "pageSize": 20,
        }
        mock_repo_cls.return_value = mock_repo

        res = await mod.list_staging_terms(
            status_filter="pending", db=mock_db, current_admin=None
        )
        assert res["total"] == 1
        assert res["items"][0]["significanceScore"] == 9
