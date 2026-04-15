"""
Tests for the JSON protocol message construction and argument
serialization.

Uses a mock session to capture messages without needing a real
WebSocket connection.
"""

import json
from unittest.mock import MagicMock

from pgwidgets.sync.widget import Widget, build_widget_class
from pgwidgets.defs import WIDGETS


class MockSession:
    """Minimal session mock that captures protocol messages."""

    def __init__(self):
        self._sent = []
        self._next_id = 1
        self._widget_map = {}
        self._root_widgets = []

    def _call(self, wid, method, *args):
        msg = {
            "type": "call",
            "id": self._next_id,
            "wid": wid,
            "method": method,
            "args": list(args),
        }
        self._next_id += 1
        self._sent.append(msg)
        return None

    def _listen(self, wid, action, handler):
        msg = {
            "type": "listen",
            "wid": wid,
            "action": action,
        }
        self._sent.append(msg)

    def _resolve_arg(self, val):
        """Convert Widget instances to wire references."""
        if isinstance(val, Widget):
            return {"__wid__": val.wid}
        return val

    def _resolve_return(self, val):
        """Convert wire references back to Widget instances."""
        if isinstance(val, dict) and "__wid__" in val:
            return self._widget_map.get(val["__wid__"], val)
        return val


def _make_widget(session, js_class="Label", wid=1):
    """Create a widget instance with the mock session."""
    cls = build_widget_class(js_class, WIDGETS[js_class])
    w = cls.__new__(cls)
    Widget.__init__(w, session, wid, js_class)
    session._widget_map[wid] = w
    return w


class TestMethodCalls:
    """Test that method calls produce correct protocol messages."""

    def test_simple_method_call(self):
        session = MockSession()
        label = _make_widget(session, "Label", wid=1)
        label.set_text("hello")

        assert len(session._sent) == 1
        msg = session._sent[0]
        assert msg["type"] == "call"
        assert msg["wid"] == 1
        assert msg["method"] == "set_text"
        assert msg["args"] == ["hello"]

    def test_method_with_multiple_args(self):
        session = MockSession()
        label = _make_widget(session, "Label", wid=2)
        label.set_color("#fff", "#000")

        msg = session._sent[0]
        assert msg["method"] == "set_color"
        assert msg["args"] == ["#fff", "#000"]

    def test_getter_returns_from_local_state(self):
        session = MockSession()
        label = _make_widget(session, "Label", wid=3)
        # Getters with matching setters return from local state
        # without sending a message to the browser.
        label.set_text("hello")
        assert label.get_text() == "hello"
        # Only the set_text call was sent, not get_text
        assert len(session._sent) == 1
        assert session._sent[0]["method"] == "set_text"

    def test_base_widget_method(self):
        session = MockSession()
        label = _make_widget(session, "Label", wid=4)
        label.resize(400, 300)

        msg = session._sent[0]
        assert msg["method"] == "resize"
        assert msg["args"] == [400, 300]

    def test_message_ids_increment(self):
        session = MockSession()
        label = _make_widget(session, "Label", wid=1)
        label.set_text("a")
        label.set_text("b")
        label.set_color("#fff", "#000")

        ids = [m["id"] for m in session._sent]
        assert ids == [1, 2, 3]


class TestArgumentSerialization:
    """Test that widget references are correctly serialized."""

    def test_widget_ref_serialized(self):
        session = MockSession()
        vbox = _make_widget(session, "VBox", wid=10)
        btn = _make_widget(session, "Button", wid=11)
        vbox.add_widget(btn, 0)

        msg = session._sent[0]
        assert msg["method"] == "add_widget"
        assert msg["args"] == [{"__wid__": 11}, 0]

    def test_primitives_pass_through(self):
        session = MockSession()
        slider = _make_widget(session, "Slider", wid=5)
        slider.set_value(42)

        msg = session._sent[0]
        assert msg["args"] == [42]

    def test_string_args_pass_through(self):
        session = MockSession()
        label = _make_widget(session, "Label", wid=6)
        label.set_text("hello world")

        msg = session._sent[0]
        assert msg["args"] == ["hello world"]

    def test_none_arg_passes_through(self):
        session = MockSession()
        label = _make_widget(session, "Label", wid=7)
        label.set_color(None, "red")

        msg = session._sent[0]
        assert msg["args"] == [None, "red"]

    def test_return_value_widget_ref_resolved(self):
        session = MockSession()
        w = _make_widget(session, "Button", wid=20)
        resolved = session._resolve_return({"__wid__": 20})
        assert resolved is w

    def test_return_value_primitive_unchanged(self):
        session = MockSession()
        assert session._resolve_return(42) == 42
        assert session._resolve_return("hello") == "hello"
        assert session._resolve_return(None) is None


class TestCallbackRegistration:
    """Test that callback registration produces correct messages."""

    def test_on_registers_listener(self):
        session = MockSession()
        btn = _make_widget(session, "Button", wid=1)
        btn.on("activated", lambda: None)

        msg = session._sent[0]
        assert msg["type"] == "listen"
        assert msg["wid"] == 1
        assert msg["action"] == "activated"

    def test_add_callback_registers_listener(self):
        session = MockSession()
        btn = _make_widget(session, "Button", wid=2)
        btn.add_callback("activated", lambda w: None)

        msg = session._sent[0]
        assert msg["type"] == "listen"
        assert msg["wid"] == 2
        assert msg["action"] == "activated"


class TestWidgetProperties:
    """Test widget instance properties."""

    def test_wid_property(self):
        session = MockSession()
        w = _make_widget(session, "Label", wid=42)
        assert w.wid == 42

    def test_session_property(self):
        session = MockSession()
        w = _make_widget(session, "Label", wid=1)
        assert w.session is session

    def test_repr(self):
        session = MockSession()
        w = _make_widget(session, "Button", wid=5)
        assert repr(w) == "<Button wid=5>"

    def test_destroy_removes_from_map(self):
        session = MockSession()
        w = _make_widget(session, "Label", wid=10)
        assert 10 in session._widget_map
        w.destroy()
        assert 10 not in session._widget_map


class TestKeywordArgs:
    """Test that generated methods handle keyword arguments."""

    def test_kwargs_mapped_to_positional(self):
        session = MockSession()
        label = _make_widget(session, "Label", wid=1)
        label.set_color(bg="#fff", fg="#000")

        msg = session._sent[0]
        assert msg["args"] == ["#fff", "#000"]

    def test_mixed_args_and_kwargs(self):
        session = MockSession()
        label = _make_widget(session, "Label", wid=1)
        label.set_color("#fff", fg="#000")

        msg = session._sent[0]
        assert msg["args"] == ["#fff", "#000"]

    def test_unknown_kwarg_raises(self):
        session = MockSession()
        label = _make_widget(session, "Label", wid=1)
        try:
            label.set_color(bg="#fff", badarg="oops")
            assert False, "Should have raised TypeError"
        except TypeError as e:
            assert "badarg" in str(e)
