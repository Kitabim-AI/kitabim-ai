from types import SimpleNamespace
from unittest.mock import MagicMock

from PIL import Image

from engine.line_ends import read_line_end_words


def _line(x0, y0, x1, y1):
    return SimpleNamespace(bbox=[x0, y0, x1, y1])


def _block(html):
    return SimpleNamespace(html=html, error=False)


def test_read_line_end_words_reads_left_edge_and_keeps_hyphenated_ends():
    image = Image.new("RGB", (1000, 400))
    detector = MagicMock(
        return_value=[
            SimpleNamespace(
                bboxes=[
                    _line(100, 300, 900, 340),  # out of order on purpose
                    _line(100, 10, 900, 50),
                    _line(100, 60, 900, 100),
                    _line(100, 110, 900, 150),
                    _line(800, 200, 900, 240),  # too narrow: a page number
                ]
            )
        ]
    )
    recognizer = MagicMock(
        return_value=[
            SimpleNamespace(
                blocks=[
                    _block("<p>ئەھۋالى ھەز-</p>"),
                    _block("<p>بىر خە -</p>"),
                    _block("<p>ئادەتتىكى ئاخىر</p>"),
                    _block("<p>بۇ ئەسەر \u2014</p>"),
                ]
            )
        ]
    )

    words = read_line_end_words(image, detector, recognizer)

    assert words == {"ھەز", "خە", "ئەسەر"}
    layout = recognizer.call_args.args[1][0]
    assert recognizer.call_args.kwargs == {"full_page": False}
    # Top-to-bottom, narrow line skipped, crop is the left (line-end) part.
    tops = [b.bbox[1] for b in layout.bboxes]
    assert tops == [10, 60, 110, 300]
    x0, _, x1, _ = layout.bboxes[0].bbox
    assert x0 == 100 and 100 < x1 < 900  # starts at the line end, not the whole line


def test_read_line_end_words_empty_when_no_lines():
    detector = MagicMock(return_value=[SimpleNamespace(bboxes=[])])
    recognizer = MagicMock()
    assert (
        read_line_end_words(Image.new("RGB", (10, 10)), detector, recognizer) == set()
    )
    recognizer.assert_not_called()


def test_read_line_end_words_maps_arabic_heh_to_uyghur_ae():
    # A narrow crop pushes the recognizer to Arabic letter forms: "خه-" for "خە-".
    detector = MagicMock(return_value=[SimpleNamespace(bboxes=[_line(0, 0, 900, 40)])])
    recognizer = MagicMock(
        return_value=[SimpleNamespace(blocks=[_block("<p>بىر خه-</p>")])]
    )
    assert read_line_end_words(Image.new("RGB", (1000, 100)), detector, recognizer) == {
        "خە"
    }
