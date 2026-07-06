import sys
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock

BACKEND_DIR = str(Path(__file__).resolve().parents[3])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[5] / "packages" / "backend-core"
)


def setup_paths():
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api."):
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


@pytest.mark.asyncio
async def test_list_surahs():
    setup_paths()
    from api.endpoints.quran_router import list_surahs

    mock_session = AsyncMock()

    mock_res = MagicMock()
    mock_res.all.return_value = [
        (1, "Al-Fatihah", "الفاتحة", "ئالفاتىھە"),
        (2, "Al-Baqarah", "البقرة", "ئالباقارە"),
    ]
    mock_session.execute.return_value = mock_res

    result = await list_surahs(session=mock_session)

    assert len(result) == 2
    assert result[0].surah == 1
    assert result[0].surah_name_ug == "ئالفاتىھە"
    assert result[1].surah_name_en == "Al-Baqarah"


@pytest.mark.asyncio
async def test_get_quran_stats():
    setup_paths()
    from api.endpoints.quran_router import get_quran_stats

    mock_session = AsyncMock()

    mock_res = MagicMock()
    mock_res.scalar.return_value = 6236
    mock_session.execute.return_value = mock_res

    result = await get_quran_stats(surah=None, session=mock_session)

    assert result["total_entries"] == 6236
