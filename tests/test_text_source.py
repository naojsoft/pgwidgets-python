"""Tests for the Python-authoritative TextSource.

The model must work with no browser connected (the UI is built headless and
replayed on connect), which is exactly the case that used to crash callers
that queried refs during construction.
"""

import pytest

from pgwidgets.sync.Widgets import TextSource
from pgwidgets.text_model import TextBufferRef


class MockSession:
    """No browser connected: _call records the message and returns None."""

    def __init__(self):
        self.sent = []
        self._next = 0
        self._widget_map = {}
        self._root_widgets = []

    def _create(self, js_class, *args):
        self._next += 1
        self.sent.append(("create", js_class, args))
        return self._next

    def _call(self, wid, method, *args):
        self.sent.append((method, list(args)))
        return None

    def _resolve_arg(self, v):
        return v

    def _resolve_return(self, v):
        return v

    def _listen(self, wid, action, handler):
        pass


def _ts():
    return TextSource(MockSession())


def test_textsource_is_handwritten():
    assert TextSource.__module__.endswith("text_source")
    # inherits base widget methods and exposes model methods at class level
    for name in ("show", "hide", "set_tooltip", "get_ref_bounds",
                 "insert_text", "create_tag", "set_editable"):
        assert hasattr(TextSource, name), name


def test_empty_bounds_offline():
    # the integgui3 crash: get_ref_bounds() must not return None offline
    tw = _ts()
    start, end = tw.get_ref_bounds()
    assert isinstance(start, TextBufferRef) and isinstance(end, TextBufferRef)
    assert start.get_offset() == 0 and end.get_offset() == 0
    tw.delete_range(start, end)  # no-op, must not raise


def test_build_and_query_offline():
    tw = _ts()
    tw.set_editable(False)
    tw.insert_text(tw.get_ref_end(), "line one\n")
    tw.insert_text(tw.get_ref_end(), "ERROR here\n")
    assert tw.get_text() == "line one\nERROR here\n"
    assert tw.get_length() == 20
    assert tw.get_ref_end().get_line() == 2
    m = tw.find("ERROR")
    assert (m[0].get_offset(), m[1].get_offset()) == (9, 14)


def test_tags_offline():
    tw = _ts()
    tw.create_tag("err", bold=True)
    tw.insert_text(tw.get_ref_end(), "abcXXXghi")
    tw.apply_tag("err", tw.create_ref(3), tw.create_ref(6))
    assert tw.has_tag("err")
    reg = tw.get_tag_region("err")
    assert (reg[0].get_offset(), reg[1].get_offset()) == (3, 6)


def test_refs_follow_edits():
    tw = _ts()
    tw.insert_text(tw.get_ref_end(), "hello")
    r = tw.create_ref(5)
    tw.insert_text(tw.get_ref_start(), "XX")
    assert r.get_offset() == 7  # shifted by the 2-char prepend


def test_changed_callback_is_model_authoritative():
    tw = _ts()
    seen = []
    tw.add_callback("changed", lambda w: seen.append(w))
    tw.insert_text(tw.get_ref_end(), "z")
    assert seen == [tw]  # fires with the widget, from a Python-side edit


def test_modified_flag():
    tw = _ts()
    assert tw.get_modified() is False
    tw.insert_text(tw.get_ref_end(), "hi")
    assert tw.get_modified() is True
    tw.mark_clean()
    assert tw.get_modified() is False
    tw.set_text("fresh")          # loading content is clean
    assert tw.get_modified() is False


def test_end_lineno():
    tw = _ts()
    tw.insert_text(tw.get_ref_end(), "a\nb\nc")
    assert tw.get_end_lineno() == 2


def test_set_font_and_scroll_push_to_browser():
    tw = _ts()
    tw.insert_text(tw.get_ref_end(), "l0\nl1\nl2")
    sess = tw._session
    sess.sent.clear()
    tw.set_font("monospace", 14)
    tw.scroll_to_lineno(2)
    tw.scroll_to_end()
    methods = [m[0] for m in sess.sent]
    assert "set_font" in methods
    # scroll helpers address the browser by offset
    offs = [m[1][0] for m in sess.sent if m[0] == "_scrollToOffset"]
    assert offs == [6, tw.get_length()]  # line 2 starts at offset 6


def test_tooltip_api_pushes_to_browser():
    tw = _ts()
    sess = tw._session
    sess.sent.clear()
    tw.set_tooltips_enabled(True)
    tw.show_tooltip("var x = 3", 100, 40)
    assert "set_tooltips_enabled" in [m[0] for m in sess.sent]
    assert ("_showTooltip", ["var x = 3", 100, 40]) in [
        (m[0], m[1]) for m in sess.sent]


def test_clear_icons_offline():
    tw = _ts()
    tw.insert_text(tw.get_ref_end(), "abc")
    tw.set_icon(tw.create_ref(0), "icon://x")
    tw.clear_icons()  # must not raise offline


def test_reconstruct_pushes_full_state():
    tw = _ts()
    tw.create_tag("t", bold=True)
    tw.insert_text(tw.get_ref_end(), "abcdef")
    tw.apply_tag("t", tw.create_ref(0), tw.create_ref(3))
    sess = tw._session
    sess.sent.clear()
    tw._reconstruct_model()
    methods = [m[0] for m in sess.sent]
    assert methods[0] == "set_text"
    assert sess.sent[0][1][0] == "abcdef"
    assert "create_tag" in methods
    assert "_restoreTagIntervals" in methods


def test_scroll_alignment_rides_along_with_the_offset():
    """A caller can ask for the target line to be centered rather than
    merely brought into view."""
    tw = _ts()
    tw.insert_text(tw.get_ref_end(), "l0\nl1\nl2")
    sess = tw._session
    sess.sent.clear()

    tw.scroll_to_lineno(2, align='center')
    tw.scroll_to_ref(tw.get_ref_line_start(1), align='top')
    tw.scroll_to_lineno(0)

    calls = [m[1] for m in sess.sent if m[0] == "_scrollToOffset"]
    assert calls == [[6, 'center'], [3, 'top'], [0, 'nearest']]


def test_an_unknown_alignment_is_rejected():
    tw = _ts()
    with pytest.raises(ValueError):
        tw.scroll_to_lineno(0, align='middle')


def test_cursor_style_is_pushed_and_remembered():
    tw = _ts()
    sess = tw._session
    assert tw.get_cursor_style() == ('line', None)
    sess.sent.clear()

    tw.set_cursor_style('block', color='indianred')

    assert ("set_cursor_style", ['block', 'indianred']) in [
        (m[0], m[1]) for m in sess.sent]
    assert tw.get_cursor_style() == ('block', 'indianred')


def test_cursor_style_is_replayed_to_a_reconnecting_browser():
    tw = _ts()
    tw.set_cursor_style('block', color='indianred')
    sess = tw._session
    sess.sent.clear()

    tw._reconstruct_model()

    assert ("set_cursor_style", ['block', 'indianred']) in [
        (m[0], m[1]) for m in sess.sent]


def test_an_unknown_cursor_style_is_rejected():
    tw = _ts()
    with pytest.raises(ValueError):
        tw.set_cursor_style('underline')
