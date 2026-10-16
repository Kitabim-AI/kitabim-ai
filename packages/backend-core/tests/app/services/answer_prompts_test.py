from app.services.chat.answer_prompts import build_answer_instructions


def test_build_answer_instructions_authorizes_verbatim_reproduction_of_source_text():
    """The Answer Agent must reproduce a poem/song/passage's full text
    verbatim (via blockquote) when the user asks to see it and the context
    contains it -- Gemini's own built-in reluctance to reproduce full
    creative works verbatim (confirmed in production: it wrote a generic
    "how to evaluate authenticity" essay instead of the retrieved poem)
    otherwise silently overrides the retrieved context with a refusal, even
    though nothing in this prompt asked for that behavior and the content is
    the user's own indexed library, retrieved specifically to answer this."""
    instructions = build_answer_instructions()

    assert "verbatim" in instructions
    assert "copyright" in instructions.lower()
    assert "blockquote" in instructions.lower() or "'>'" in instructions


def test_build_answer_instructions_strict_no_answer_unaffected():
    # strict_no_answer is a separate, currently-unused-in-production branch --
    # confirm this change doesn't accidentally affect it.
    instructions = build_answer_instructions(strict_no_answer=True)
    assert "verbatim" not in instructions


def test_reader_mode_prefers_current_volume_then_names_other_volume():
    """Reader chat gets sister-volume passages alongside the open volume's: the
    answer must come from the open volume when it can, and otherwise say the
    open volume doesn't cover it and cite the other volume explicitly."""
    instructions = build_answer_instructions(
        is_global=False, current_book_id="cur123", current_volume=1
    )

    assert "BookID: cur123" in instructions
    assert "Volume 1" in instructions
    assert "other volume" in instructions.lower()


def test_current_volume_rule_absent_in_global_chat():
    instructions = build_answer_instructions(
        is_global=True, current_book_id="cur123", current_volume=1
    )
    assert "BookID: cur123" not in instructions


def test_current_volume_rule_absent_without_current_book():
    assert "currently reading" not in build_answer_instructions(is_global=False)
