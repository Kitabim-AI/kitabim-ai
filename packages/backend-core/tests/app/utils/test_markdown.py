import pytest
from app.utils.markdown import normalize_markdown, strip_markdown

def test_normalize_markdown():
    # Empty cases
    assert normalize_markdown("") == ""
    assert normalize_markdown(None) == ""
    
    # Newline replacement
    assert normalize_markdown("line1\r\nline2\rline3\n") == "line1\nline2\nline3"
    
    # Trailing whitespace removal
    assert normalize_markdown("trailing   \nspaces   \n") == "trailing\nspaces"
    
    # Consecutiv newlines reduction
    assert normalize_markdown("a\n\n\n\nb") == "a\n\nb"

def test_strip_markdown():
    # Empty cases
    assert strip_markdown("") == ""
    assert strip_markdown(None) == ""
    
    # Headers
    assert strip_markdown("### Heading 3") == "Heading 3"
    assert strip_markdown("# Main Heading") == "Main Heading"
    
    # Blockquotes
    assert strip_markdown("> Quote") == "Quote"
    
    # Lists
    assert strip_markdown("- Item 1\n* Item 2\n+ Item 3") == "Item 1\nItem 2\nItem 3"
    assert strip_markdown("1. Item 1\n2) Item 2") == "Item 1\nItem 2"
    
    # Horizontal rules
    assert strip_markdown("---") == ""
    assert strip_markdown("***") == ""
    
    # Links & Images
    assert strip_markdown("![Alt text](image.png)") == "Alt text"
    assert strip_markdown("[Link text](https://google.com)") == "Link text"
    
    # Code
    assert strip_markdown("`inline code`") == "inline code"
    
    # Bold / Italic
    assert strip_markdown("**bold** and __bold__") == "bold and bold"
    assert strip_markdown("*italic* and _italic_") == "italic and italic"
    
    # Complex combination
    assert strip_markdown("## Heading\n\n- **Bold** item\n- [Link](url)") == "Heading\nBold item\nLink"
