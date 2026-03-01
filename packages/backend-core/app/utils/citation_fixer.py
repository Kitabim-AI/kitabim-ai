"""
Utility to fix malformed citation references in LLM responses.

The LLM sometimes generates incomplete markdown links for citations.
This module detects and fixes common malformation patterns.
"""
import re
import logging

logger = logging.getLogger(__name__)


def fix_malformed_citations(text: str) -> str:
    """
    Fix malformed citation references in LLM output.

    Detects patterns like:
    - "ref:26]بەت179 ،178" (missing opening bracket and proper markdown format)
    - Incomplete markdown links

    Converts them to proper format: [citation text](ref:book_id:page1,page2)

    Args:
        text: The LLM response text potentially containing malformed citations

    Returns:
        Text with fixed citation markdown links
    """
    if not text:
        return text

    # Pattern 0: Detect nested markdown like [display text]([link text](ref:ID:pages))
    # The LLM sometimes wraps a ref: URL inside another markdown link, e.g.:
    #   [book title, 14-page]([مەنبە](ref:bookId:14))
    # Convert to proper: [display text](ref:ID:pages)
    pattern0 = r'\[([^\]]+)\]\(\[[^\]]*\]\((ref:[^)]+)\)\)'

    def replace_pattern0(match):
        display_text = match.group(1)
        ref_url = match.group(2)
        result = f"[{display_text}]({ref_url})"
        logger.info(f"Fixed nested markdown reference -> [{display_text}]({ref_url})")
        return result

    text = re.sub(pattern0, replace_pattern0, text)

    # Pattern 1: Detect "ref:ID]بەت..." where the opening "[" and proper markdown is missing
    # This pattern looks for: ref:ID]بەت page_numbers text
    # Example: "ref:26]بەت179 ،178 ،2 ،ئوتوم (ئايۇز رىسانياۇ) نىخىرات تۆزۈۇغ :ەنەدم"
    # Note: The word بەت comes BEFORE the page numbers
    pattern1 = r'ref:(\d+)\]بەت\s*([\d\s،]+)(.*?)(?=\s*(?:ref:|$|\[))'

    def replace_pattern1(match):
        book_id = match.group(1)
        pages_str = match.group(2).strip()
        citation_text = match.group(3).strip()

        # Extract page numbers (they might be separated by Arabic comma ، or space)
        page_numbers = re.findall(r'\d+', pages_str)
        pages = ','.join(page_numbers)

        # Build proper markdown link
        # The format should be: [source info](ref:id:pages)
        # Example: [تاريخى نۇرى، 2-توم، 178، 179 بەت](ref:26:178,179)

        if pages:
            # Build proper markdown link
            if citation_text:
                # Clean up citation text - remove leading punctuation
                citation_text = citation_text.lstrip('،').strip()
                pages_display = '، '.join(page_numbers)
                full_citation = f"{citation_text}، {pages_display} بەت"
            else:
                pages_display = '، '.join(page_numbers)
                full_citation = f"{pages_display} بەت"

            result = f"[{full_citation}](ref:{book_id}:{pages})"
            logger.info(f"Fixed malformed citation: ref:{book_id}]بەت{pages_str}{citation_text} -> [{full_citation}](ref:{book_id}:{pages})")
            return result

        # If we can't parse it properly, return original
        return match.group(0)

    text = re.sub(pattern1, replace_pattern1, text)

    # Pattern 2: Detect standalone "ref:ID:" without proper markdown
    # Example: "text ref:26:178,179 more text" should become "text [مەنبە](ref:26:178,179) more text"
    pattern2 = r'(?<!\])\bref:(\w+):(\d+(?:,\d+)*)\b(?!\))'

    def replace_pattern2(match):
        book_id = match.group(1)
        pages = match.group(2)

        # Create a generic citation text
        result = f"[مەنبە](ref:{book_id}:{pages})"
        logger.info(f"Fixed standalone reference: ref:{book_id}:{pages} -> [مەنبە](ref:{book_id}:{pages})")
        return result

    text = re.sub(pattern2, replace_pattern2, text)

    return text
