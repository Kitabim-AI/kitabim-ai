import sys
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock

BACKEND_DIR = str(Path(__file__).resolve().parents[3])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[5] / "packages" / "backend-core"
)


def setup_paths():
    # Force reload of api modules to avoid cache shadowing from tests/api
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api."):
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


def test_stats_basic():
    """Basic unit test scaffold for stats."""
    assert True


def _make_rag_row(
    total=0,
    thumbs_up=0,
    thumbs_down=0,
    avg_faithfulness=None,
    avg_answer_relevance=None,
    avg_context_precision=None,
):
    row = MagicMock()
    row.total = total
    row.thumbs_up = thumbs_up
    row.thumbs_down = thumbs_down
    row.avg_faithfulness = avg_faithfulness
    row.avg_answer_relevance = avg_answer_relevance
    row.avg_context_precision = avg_context_precision
    return row


@pytest.mark.asyncio
async def test_get_rag_quality_stats_computes_real_averages():
    setup_paths()
    from api.endpoints.stats_router import get_rag_quality_stats

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = _make_rag_row(
        total=10,
        thumbs_up=6,
        thumbs_down=2,
        avg_faithfulness=0.82,
        avg_answer_relevance=0.91,
        avg_context_precision=0.75,
    )
    session.execute.return_value = mock_result

    stats = await get_rag_quality_stats(current_user={"role": "admin"}, session=session)

    assert stats["total_evaluations"] == 10
    assert stats["graded_evaluations"] == 8
    assert stats["thumbs_up_count"] == 6
    assert stats["thumbs_down_count"] == 2
    assert stats["avg_faithfulness"] == 0.82
    assert stats["avg_answer_relevance"] == 0.91
    assert stats["avg_context_precision"] == 0.75


@pytest.mark.asyncio
async def test_get_rag_quality_stats_no_scored_rows_yet():
    """Before any rag_eval_job has run (or the feature is disabled), the
    aggregate scores must be None, not 0 or a crash."""
    setup_paths()
    from api.endpoints.stats_router import get_rag_quality_stats

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = _make_rag_row(total=5)
    session.execute.return_value = mock_result

    stats = await get_rag_quality_stats(current_user={"role": "admin"}, session=session)

    assert stats["total_evaluations"] == 5
    assert stats["avg_faithfulness"] is None
    assert stats["avg_answer_relevance"] is None
    assert stats["avg_context_precision"] is None
