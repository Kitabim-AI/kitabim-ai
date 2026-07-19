import sys
from pathlib import Path

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


def test_spell_check_basic():
    """Basic unit test scaffold for spell_check."""
    assert True


def test_issue_to_out_attaches_confidence_per_candidate():
    setup_paths()
    from api.endpoints.spell_check_router import _issue_to_out  # type: ignore[import]
    from app.db.models import PageSpellIssue

    issue = PageSpellIssue(
        id=1,
        page_id=1,
        word="بو",
        char_offset=0,
        char_end=2,
        ocr_corrections=["بۇ"],
        status="open",
    )

    out = _issue_to_out(issue)

    assert out.id == 1
    assert out.word == "بو"
    assert len(out.ocr_corrections) == 1
    assert out.ocr_corrections[0].word == "بۇ"
    assert 0 < out.ocr_corrections[0].confidence <= 1


def test_issue_to_out_splits_confidence_across_multiple_candidates():
    setup_paths()
    from api.endpoints.spell_check_router import _issue_to_out  # type: ignore[import]
    from app.db.models import PageSpellIssue

    issue = PageSpellIssue(
        id=2,
        page_id=1,
        word="بو",
        char_offset=0,
        char_end=2,
        ocr_corrections=["بۇ", "بۋ"],
        status="open",
    )

    out = _issue_to_out(issue)

    words = {c.word for c in out.ocr_corrections}
    assert words == {"بۇ", "بۋ"}

    single = (
        _issue_to_out(
            PageSpellIssue(
                id=3,
                page_id=1,
                word="بو",
                char_offset=0,
                char_end=2,
                ocr_corrections=["بۇ"],
                status="open",
            )
        )
        .ocr_corrections[0]
        .confidence
    )
    # Two competing candidates should each score lower than a single candidate would.
    for c in out.ocr_corrections:
        assert c.confidence < single


def test_issue_to_out_no_corrections():
    setup_paths()
    from api.endpoints.spell_check_router import _issue_to_out  # type: ignore[import]
    from app.db.models import PageSpellIssue

    issue = PageSpellIssue(
        id=4,
        page_id=1,
        word="بو",
        char_offset=0,
        char_end=2,
        ocr_corrections=[],
        status="open",
    )

    out = _issue_to_out(issue)

    assert out.ocr_corrections == []
