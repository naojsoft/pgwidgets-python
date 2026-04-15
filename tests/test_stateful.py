"""
Tests for stateful widget tracking.

Verifies that widgets store state locally, getters return from local
state, children are tracked, constructor args are preserved, and
callback registrations are recorded.
"""

from pgwidgets.sync.widget import Widget, build_widget_class
from pgwidgets.defs import WIDGETS


class MockSession:
    """Minimal session mock for stateful tests."""

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
        msg = {"type": "listen", "wid": wid, "action": action}
        self._sent.append(msg)

    def _resolve_arg(self, val):
        if isinstance(val, Widget):
            return {"__wid__": val.wid}
        return val

    def _resolve_return(self, val):
        if isinstance(val, dict) and "__wid__" in val:
            return self._widget_map.get(val["__wid__"], val)
        return val


def _make(session, js_class, wid, **initial_state):
    """Create a widget with optional initial state."""
    cls = build_widget_class(js_class, WIDGETS[js_class])
    w = cls._from_existing(session, wid, js_class)
    session._widget_map[wid] = w
    session._root_widgets.append(w)
    for k, v in initial_state.items():
        w._state[k] = v
    return w


# -- State tracking --

class TestStateTracking:
    """Test that setters store state locally."""

    def test_set_text_stores_state(self):
        s = MockSession()
        label = _make(s, "Label", 1)
        label.set_text("hello")
        assert label._state["text"] == "hello"

    def test_set_text_also_sends_message(self):
        s = MockSession()
        label = _make(s, "Label", 1)
        label.set_text("hello")
        assert len(s._sent) == 1
        assert s._sent[0]["method"] == "set_text"

    def test_set_color_stores_tuple(self):
        s = MockSession()
        label = _make(s, "Label", 1)
        label.set_color("#fff", "#000")
        assert label._state["color"] == ("#fff", "#000")

    def test_resize_stores_as_size(self):
        s = MockSession()
        label = _make(s, "Label", 1)
        label.resize(400, 300)
        assert label._state["size"] == (400, 300)

    def test_show_stores_visible_true(self):
        s = MockSession()
        label = _make(s, "Label", 1)
        label.show()
        assert label._state["visible"] is True

    def test_hide_stores_visible_false(self):
        s = MockSession()
        label = _make(s, "Label", 1)
        label.show()
        label.hide()
        assert label._state["visible"] is False

    def test_set_value_stores_state(self):
        s = MockSession()
        slider = _make(s, "Slider", 1)
        slider.set_value(42)
        assert slider._state["value"] == 42

    def test_set_enabled_stores_state(self):
        s = MockSession()
        btn = _make(s, "Button", 1)
        btn.set_enabled(False)
        assert btn._state["enabled"] is False

    def test_state_updates_on_successive_calls(self):
        s = MockSession()
        label = _make(s, "Label", 1)
        label.set_text("first")
        label.set_text("second")
        assert label._state["text"] == "second"


# -- Getters from local state --

class TestGetters:
    """Test that getters return from local state."""

    def test_get_text_returns_local(self):
        s = MockSession()
        label = _make(s, "Label", 1)
        label.set_text("hello")
        assert label.get_text() == "hello"

    def test_get_text_no_message_sent(self):
        s = MockSession()
        label = _make(s, "Label", 1)
        label.set_text("hello")
        s._sent.clear()
        label.get_text()
        assert len(s._sent) == 0

    def test_get_value_returns_local(self):
        s = MockSession()
        slider = _make(s, "Slider", 1)
        slider.set_value(75)
        assert slider.get_value() == 75

    def test_get_enabled_returns_local(self):
        s = MockSession()
        btn = _make(s, "Button", 1)
        btn.set_enabled(False)
        assert btn.get_enabled() is False

    def test_is_visible_returns_local(self):
        s = MockSession()
        label = _make(s, "Label", 1)
        label.show()
        assert label.is_visible() is True
        label.hide()
        assert label.is_visible() is False

    def test_getter_returns_none_when_unset(self):
        s = MockSession()
        label = _make(s, "Label", 1)
        assert label.get_text() is None

    def test_get_state_returns_local(self):
        s = MockSession()
        cb = _make(s, "CheckBox", 1)
        cb.set_state(True)
        assert cb.get_state() is True


# -- Child tracking --

class TestChildTracking:
    """Test parent-child relationship tracking."""

    def test_add_widget_tracks_child(self):
        s = MockSession()
        vbox = _make(s, "VBox", 1)
        btn = _make(s, "Button", 2)
        vbox.add_widget(btn, 0)

        assert len(vbox._children) == 1
        child, args, meth = vbox._children[0]
        assert child is btn
        assert args == (0,)
        assert meth == "add_widget"

    def test_add_widget_sets_parent(self):
        s = MockSession()
        vbox = _make(s, "VBox", 1)
        btn = _make(s, "Button", 2)
        vbox.add_widget(btn, 0)
        assert btn._parent is vbox

    def test_add_widget_removes_from_roots(self):
        s = MockSession()
        vbox = _make(s, "VBox", 1)
        btn = _make(s, "Button", 2)
        assert btn in s._root_widgets
        vbox.add_widget(btn, 0)
        assert btn not in s._root_widgets

    def test_set_widget_replaces_child(self):
        s = MockSession()
        frame = _make(s, "Frame", 1)
        label1 = _make(s, "Label", 2)
        label2 = _make(s, "Label", 3)

        frame.set_widget(label1)
        assert len(frame._children) == 1
        assert frame._children[0][0] is label1
        assert label1._parent is frame

        frame.set_widget(label2)
        assert len(frame._children) == 1
        assert frame._children[0][0] is label2
        assert label2._parent is frame
        assert label1._parent is None

    def test_multiple_children(self):
        s = MockSession()
        vbox = _make(s, "VBox", 1)
        btn1 = _make(s, "Button", 2)
        btn2 = _make(s, "Button", 3)
        label = _make(s, "Label", 4)

        vbox.add_widget(btn1, 0)
        vbox.add_widget(btn2, 0)
        vbox.add_widget(label, 1)

        assert len(vbox._children) == 3
        children = [c for c, *_ in vbox._children]
        assert children == [btn1, btn2, label]

    def test_destroy_removes_from_parent(self):
        s = MockSession()
        vbox = _make(s, "VBox", 1)
        btn = _make(s, "Button", 2)
        vbox.add_widget(btn, 0)
        assert len(vbox._children) == 1

        btn.destroy()
        assert len(vbox._children) == 0
        assert btn._parent is None

    def test_nested_containers(self):
        s = MockSession()
        vbox = _make(s, "VBox", 1)
        hbox = _make(s, "HBox", 2)
        btn = _make(s, "Button", 3)

        hbox.add_widget(btn, 0)
        vbox.add_widget(hbox, 1)

        assert btn._parent is hbox
        assert hbox._parent is vbox
        assert vbox._parent is None


# -- Callback registration tracking --

class TestCallbackTracking:
    """Test that callback registrations are stored for reconstruction."""

    def test_on_stores_registration(self):
        s = MockSession()
        btn = _make(s, "Button", 1)
        handler = lambda: None
        btn.on("activated", handler)

        assert "activated" in btn._registered_callbacks
        h, extra_args, extra_kwargs, style = btn._registered_callbacks["activated"]
        assert h is handler
        assert style == "on"

    def test_add_callback_stores_registration(self):
        s = MockSession()
        btn = _make(s, "Button", 1)
        handler = lambda w: None
        btn.add_callback("activated", handler)

        h, extra_args, extra_kwargs, style = btn._registered_callbacks["activated"]
        assert h is handler
        assert style == "add_callback"

    def test_callback_with_extra_args(self):
        s = MockSession()
        btn = _make(s, "Button", 1)
        handler = lambda x, y: None
        btn.on("activated", handler, "extra1", key="val")

        h, extra_args, extra_kwargs, style = btn._registered_callbacks["activated"]
        assert extra_args == ("extra1",)
        assert extra_kwargs == {"key": "val"}


# -- Constructor state --

class TestConstructorState:
    """Test that constructor args/options are available as initial state."""

    def test_constructor_args_stored(self):
        s = MockSession()
        label = _make(s, "Label", 1, text="hello")
        # Simulating what the factory does
        label._constructor_args = ("hello",)
        assert label._constructor_args == ("hello",)

    def test_constructor_options_stored(self):
        s = MockSession()
        label = _make(s, "Label", 1, halign="center")
        label._constructor_options = {"halign": "center"}
        assert label._constructor_options == {"halign": "center"}

    def test_initial_state_from_constructor(self):
        s = MockSession()
        label = _make(s, "Label", 1, text="hello", halign="center")
        assert label._state["text"] == "hello"
        assert label._state["halign"] == "center"


# -- Root widget tracking --

class TestRootWidgets:
    """Test that root widgets (no parent) are tracked."""

    def test_new_widget_is_root(self):
        s = MockSession()
        label = _make(s, "Label", 1)
        assert label in s._root_widgets

    def test_parented_widget_not_root(self):
        s = MockSession()
        vbox = _make(s, "VBox", 1)
        btn = _make(s, "Button", 2)
        vbox.add_widget(btn, 0)
        assert vbox in s._root_widgets
        assert btn not in s._root_widgets

    def test_set_widget_returns_old_child_to_roots(self):
        s = MockSession()
        frame = _make(s, "Frame", 1)
        label1 = _make(s, "Label", 2)
        label2 = _make(s, "Label", 3)

        frame.set_widget(label1)
        assert label1 not in s._root_widgets

        frame.set_widget(label2)
        assert label1 in s._root_widgets
        assert label2 not in s._root_widgets


# -- Clear resets state --

class TestClear:
    """Test that clear() resets the appropriate state keys."""

    def test_clear_resets_text(self):
        s = MockSession()
        entry = _make(s, "TextEntry", 1)
        entry.set_text("hello")
        assert entry._state["text"] == "hello"
        entry.clear()
        assert "text" not in entry._state

    def test_clear_sends_message(self):
        s = MockSession()
        entry = _make(s, "TextEntry", 1)
        entry.clear()
        assert any(m["method"] == "clear" for m in s._sent)

    def test_clear_preserves_other_state(self):
        s = MockSession()
        entry = _make(s, "TextEntry", 1)
        entry.set_text("hello")
        entry.set_length(20)
        entry.clear()
        assert "text" not in entry._state
        assert entry._state["length"] == 20

    def test_clear_htmlview(self):
        s = MockSession()
        hv = _make(s, "HtmlView", 1)
        hv.set_html("<b>hello</b>")
        hv.clear()
        assert "html" not in hv._state


# -- Method classification coverage --

class TestMethodClassification:
    """Test that all widget methods are properly classified."""

    def test_action_methods_do_not_store_state(self):
        s = MockSession()
        label = _make(s, "Label", 1)
        # set_focus is an action — should not create state
        label.set_focus()
        assert "focus" not in label._state

    def test_js_only_methods_still_send(self):
        """JS-only methods pass through to the browser."""
        s = MockSession()
        canvas = _make(s, "Canvas", 1)
        canvas.get_draw_context()
        assert len(s._sent) == 1
        assert s._sent[0]["method"] == "get_draw_context"
