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
