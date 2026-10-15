import pytest
from unittest.mock import AsyncMock, patch

from app.services.llm_spell_check_service import (
    build_correction_prompt,
    correct_page_text,
    _validate_correction,
)


def test_build_correction_prompt_includes_prev_and_next_context():
    prompt = build_correction_prompt("PAGE TEXT", "PREV TEXT", "NEXT TEXT")
    assert "PAGE TEXT" in prompt
    assert "PREV TEXT" in prompt
    assert "NEXT TEXT" in prompt
    # Context sections must be clearly delimited from the page to correct.
    assert "previous page (context only, do not correct)" in prompt
    assert "next page (context only, do not correct)" in prompt


def test_build_correction_prompt_handles_missing_context():
    prompt = build_correction_prompt("PAGE TEXT", None, None)
    assert "PAGE TEXT" in prompt
    # Should not raise, and should not literally embed the string "None".
    assert "None" not in prompt


def test_validate_correction_rejects_empty_output():
    with pytest.raises(ValueError):
        _validate_correction("some original text", "")


def test_validate_correction_rejects_whitespace_only_output():
    with pytest.raises(ValueError):
        _validate_correction("some original text", "   ")


def test_validate_correction_rejects_large_length_deviation():
    original = "a" * 1000
    corrected = "a" * 500  # 50% shorter — over the ~30% guardrail
    with pytest.raises(ValueError):
        _validate_correction(original, corrected)


def test_validate_correction_accepts_small_length_deviation():
    original = "a" * 1000
    corrected = "a" * 1100  # 10% longer — within the guardrail
    _validate_correction(original, corrected)  # should not raise


@pytest.mark.asyncio
async def test_correct_page_text_reads_model_from_system_configs():
    mock_config_repo = AsyncMock()
    mock_config_repo.get_value.return_value = "gemini-3.1-flash-lite"

    with patch("app.services.llm_spell_check_service.build_text_llm") as mock_build_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = "corrected page text"
        mock_build_llm.return_value = mock_llm

        result = await correct_page_text(
            "original page text", "prev", "next", mock_config_repo
        )

        assert result == "corrected page text"
        mock_config_repo.get_value.assert_called_once_with(
            "gemini_llm_spell_check_model", "gemini-3.1-flash-lite"
        )
        mock_build_llm.assert_called_once_with("gemini-3.1-flash-lite")
        mock_llm.ainvoke.assert_called_once()


@pytest.mark.asyncio
async def test_correct_page_text_raises_on_empty_model_output():
    mock_config_repo = AsyncMock()
    mock_config_repo.get_value.return_value = "gemini-3.1-flash-lite"

    with patch("app.services.llm_spell_check_service.build_text_llm") as mock_build_llm:
        mock_llm = AsyncMock()
        mock_llm.ainvoke.return_value = ""
        mock_build_llm.return_value = mock_llm

        with pytest.raises(ValueError):
            await correct_page_text("original page text", None, None, mock_config_repo)


@pytest.mark.asyncio
async def test_correct_page_text_normalizes_uyghur_and_markdown():
    from app.services.llm_spell_check_service import correct_page_text

    mock_config_repo = AsyncMock()
    mock_config_repo.get_value.return_value = "gemini-3.1-flash-lite"

    with patch("app.services.llm_spell_check_service.build_text_llm") as mock_build_llm:
        mock_llm = AsyncMock()
        # Arabic Teh Marbuta (\u0629) should be normalized to Uyghur E (\u06D5)
        mock_llm.ainvoke.return_value = "بۇ بىر كىتاب\u0629"
        mock_build_llm.return_value = mock_llm

        res = await correct_page_text("بۇ بىر كىتابى", None, None, mock_config_repo)
        assert "\u0629" not in res
        assert "\u06d5" in res


@pytest.mark.asyncio
async def test_apply_llm_page_correction_updates_text_and_clears_issues():
    from app.services.llm_spell_check_service import apply_llm_page_correction
    from app.db.models import Page
    from app.core.pipeline import PAGE_MILESTONE_IDLE, PAGE_MILESTONE_SUCCEEDED

    session = AsyncMock()
    page = Page(
        id=123,
        book_id="b1",
        page_number=5,
        text="بۇ بىر ياخشى كىتاپ",
        spell_check_milestone="succeeded",
        llm_spell_check_status="in_progress",
    )

    changed = await apply_llm_page_correction(session, page, "بۇ بىر ياخشى كىتاب")

    assert changed is True
    assert page.prev_text == "بۇ بىر ياخشى كىتاپ"
    assert page.text == "بۇ بىر ياخشى كىتاب"
    assert page.spell_check_milestone == PAGE_MILESTONE_IDLE
    assert page.llm_spell_check_status == PAGE_MILESTONE_SUCCEEDED
    assert page.llm_spell_check_at is not None
    assert session.execute.called


@pytest.mark.asyncio
async def test_apply_llm_page_correction_no_change_when_text_identical():
    from app.services.llm_spell_check_service import apply_llm_page_correction
    from app.db.models import Page
    from app.core.pipeline import PAGE_MILESTONE_SUCCEEDED

    session = AsyncMock()
    page = Page(
        id=123,
        book_id="b1",
        page_number=5,
        text="بۇ بىر ياخشى كىتاب",
        spell_check_milestone="succeeded",
        llm_spell_check_status="in_progress",
        prev_text=None,
    )

    changed = await apply_llm_page_correction(session, page, "بۇ بىر ياخشى كىتاب")

    assert changed is False
    assert page.prev_text is None
    assert page.spell_check_milestone == "succeeded"
    assert page.llm_spell_check_status == PAGE_MILESTONE_SUCCEEDED
    assert not session.execute.called
