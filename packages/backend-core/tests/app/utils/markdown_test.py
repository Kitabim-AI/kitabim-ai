from app.utils.markdown import normalize_markdown, strip_markdown

def test_normalize_markdown():
    assert normalize_markdown("") == ""
    assert normalize_markdown(None) == ""
    text = "Line 1\r\nLine 2\rLine 3  \n\n\nLine 4"
    expected = "Line 1\nLine 2\nLine 3\n\nLine 4"
    assert normalize_markdown(text) == expected

def test_strip_markdown():
    assert strip_markdown("") == ""
    assert strip_markdown(None) == ""
    text = """# Header
> Blockquote
- List item
1. Numbered item
---
![Image](url)
[Link](url)
**Bold** and *Italic*
`code`
"""
    expected = """Header
Blockquote
List item
Numbered item

Image
Link
Bold and Italic
code"""
    assert strip_markdown(text) == expected
