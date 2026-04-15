"""
Tests for Phase 3: Widget tree reconstruction.

Verifies that Session.reconstruct() replays the correct sequence of
create, state-setter, child-attachment, and callback-registration
messages to recreate the UI in a newly connected browser.
"""

import threading
from unittest.mock import MagicMock

from pgwidgets.sync.application import Application, Session
from pgwidgets.sync.widget import build_all_widget_classes
from pgwidgets.defs import WIDGETS


class RecordingSession(Session):
    """A Session subclass that records messages instead of sending them
    over a real WebSocket.

    During reconstruction we need _send to return a fake result so
    that _call can extract result.get("value").
    """

    def __init__(self, app, session_id):
        super().__init__(app, session_id, ws=None)
        self._recorded = []
        self._recording = False

    def _send(self, msg):
        if self._recording:
            self._recorded.append(dict(msg))
            # Return a fake result so _call doesn't crash
            return {"type": "result", "value": None}
        # During setup (widget creation), just return None (no connection)
        return None

    def start_recording(self):
        """Start capturing messages (call before reconstruct)."""
        self._recorded = []
        self._recording = True

    def stop_recording(self):
        self._recording = False


def _make_app():
    """Create a minimal Application without starting servers."""
    app = Application.__new__(Application)
    app._host = "127.0.0.1"
    app._ws_port = 9500
    app._http_port = 9501
    app._use_http_server = False
    app._concurrency = "concurrent"
    app._max_sessions = None
    app._sessions = {}
    app._next_session_id = 1
    app._session_lock = threading.Lock()
    app._on_connect = None
    app._on_disconnect = None
    app._cb_queue = None
    app._loop = None
    app._thread = None
    app._session_semaphore = None
    app._widget_classes = build_all_widget_classes()

    import logging
    logger = logging.getLogger("pgwidgets.test")
    logger.addHandler(logging.NullHandler())
    app._logger = logger

    return app


def _make_session(app=None):
    """Create a RecordingSession with widget factories."""
    if app is None:
        app = _make_app()
    s = RecordingSession(app, 1)
    s._widget_classes = app._widget_classes
    app._sessions[1] = s
    return s


class TestReconstructCreation:
    """Test that reconstruct sends create messages."""

    def test_single_widget_creates(self):
        s = _make_session()
        W = s.get_widgets()
        label = W.Label("hello")

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        creates = [m for m in s._recorded if m.get("type") == "create"]
        assert len(creates) == 1
        assert creates[0]["class"] == "Label"
        assert creates[0]["wid"] == label.wid
        assert creates[0]["args"] == ["hello"]

    def test_multiple_widgets_create(self):
        s = _make_session()
        W = s.get_widgets()
        label = W.Label("hi")
        btn = W.Button("click")

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        creates = [m for m in s._recorded if m.get("type") == "create"]
        assert len(creates) == 2
        classes = [c["class"] for c in creates]
        assert "Label" in classes
        assert "Button" in classes

    def test_constructor_with_options(self):
        s = _make_session()
        W = s.get_widgets()
        label = W.Label("hello", halign="center")

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        creates = [m for m in s._recorded if m.get("type") == "create"]
        assert len(creates) == 1
        assert creates[0]["args"] == ["hello", {"halign": "center"}]


class TestReconstructState:
    """Test that reconstruct replays state changes."""

    def test_state_changed_after_construction(self):
        s = _make_session()
        W = s.get_widgets()
        label = W.Label("hello")
        label.set_text("world")

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        calls = [m for m in s._recorded if m.get("type") == "call"]
        set_text_calls = [c for c in calls if c["method"] == "set_text"]
        assert len(set_text_calls) == 1
        assert set_text_calls[0]["args"] == ["world"]

    def test_state_unchanged_from_constructor_skipped(self):
        s = _make_session()
        W = s.get_widgets()
        label = W.Label("hello")
        # Don't change text — it should not be replayed

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        calls = [m for m in s._recorded if m.get("type") == "call"]
        set_text_calls = [c for c in calls if c["method"] == "set_text"]
        assert len(set_text_calls) == 0

    def test_color_state_replayed(self):
        s = _make_session()
        W = s.get_widgets()
        label = W.Label("hi")
        label.set_color("#fff", "#000")

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        calls = [m for m in s._recorded if m.get("type") == "call"]
        color_calls = [c for c in calls if c["method"] == "set_color"]
        assert len(color_calls) == 1
        assert color_calls[0]["args"] == ["#fff", "#000"]

    def test_resize_replayed_as_resize(self):
        s = _make_session()
        W = s.get_widgets()
        label = W.Label("hi")
        label.resize(400, 300)

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        calls = [m for m in s._recorded if m.get("type") == "call"]
        resize_calls = [c for c in calls if c["method"] == "resize"]
        assert len(resize_calls) == 1
        assert resize_calls[0]["args"] == [400, 300]

    def test_show_replayed(self):
        s = _make_session()
        W = s.get_widgets()
        label = W.Label("hi")
        label.show()

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        calls = [m for m in s._recorded if m.get("type") == "call"]
        show_calls = [c for c in calls if c["method"] == "show"]
        assert len(show_calls) == 1

    def test_hide_replayed(self):
        s = _make_session()
        W = s.get_widgets()
        label = W.Label("hi")
        label.show()
        label.hide()

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        calls = [m for m in s._recorded if m.get("type") == "call"]
        # visible is False -> hide
        hide_calls = [c for c in calls if c["method"] == "hide"]
        assert len(hide_calls) == 1
        # show should NOT be replayed (only final state matters)
        show_calls = [c for c in calls if c["method"] == "show"]
        assert len(show_calls) == 0

    def test_option_unchanged_from_constructor_skipped(self):
        s = _make_session()
        W = s.get_widgets()
        label = W.Label("hello", halign="center")
        # Don't change halign — it should not be replayed

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        calls = [m for m in s._recorded if m.get("type") == "call"]
        halign_calls = [c for c in calls if c["method"] == "set_halign"]
        assert len(halign_calls) == 0


class TestReconstructChildren:
    """Test that reconstruct replays child attachments."""

    def test_add_widget_replayed(self):
        s = _make_session()
        W = s.get_widgets()
        vbox = W.VBox()
        btn = W.Button("click")
        vbox.add_widget(btn, 0)

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        calls = [m for m in s._recorded if m.get("type") == "call"]
        add_calls = [c for c in calls if c["method"] == "add_widget"]
        assert len(add_calls) == 1
        assert add_calls[0]["wid"] == vbox.wid
        assert add_calls[0]["args"] == [{"__wid__": btn.wid}, 0]

    def test_set_widget_replayed(self):
        s = _make_session()
        W = s.get_widgets()
        frame = W.Frame()
        label = W.Label("inside")
        frame.set_widget(label)

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        calls = [m for m in s._recorded if m.get("type") == "call"]
        set_calls = [c for c in calls if c["method"] == "set_widget"]
        assert len(set_calls) == 1
        assert set_calls[0]["wid"] == frame.wid
        assert set_calls[0]["args"] == [{"__wid__": label.wid}]

    def test_multiple_children_replayed(self):
        s = _make_session()
        W = s.get_widgets()
        vbox = W.VBox()
        btn1 = W.Button("a")
        btn2 = W.Button("b")
        vbox.add_widget(btn1, 0)
        vbox.add_widget(btn2, 1)

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        calls = [m for m in s._recorded if m.get("type") == "call"]
        add_calls = [c for c in calls if c["method"] == "add_widget"]
        assert len(add_calls) == 2

    def test_nested_tree_order(self):
        """Parents are created before children."""
        s = _make_session()
        W = s.get_widgets()
        vbox = W.VBox()
        hbox = W.HBox()
        btn = W.Button("deep")
        hbox.add_widget(btn, 0)
        vbox.add_widget(hbox, 0)

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        creates = [m for m in s._recorded if m.get("type") == "create"]
        wids = [c["wid"] for c in creates]
        # vbox should be created before hbox, hbox before btn
        assert wids.index(vbox.wid) < wids.index(hbox.wid)
        assert wids.index(hbox.wid) < wids.index(btn.wid)

    def test_root_widgets_not_attached(self):
        """Root widgets should not have add_widget calls."""
        s = _make_session()
        W = s.get_widgets()
        label = W.Label("root")

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        calls = [m for m in s._recorded if m.get("type") == "call"]
        add_calls = [c for c in calls
                     if c["method"] in ("add_widget", "set_widget")]
        assert len(add_calls) == 0


class TestReconstructCallbacks:
    """Test that reconstruct re-registers callbacks."""

    def _user_listens(self, recorded):
        """Filter out auto-sync listeners, returning only user-registered ones."""
        from pgwidgets.method_types import STATE_SYNC_CALLBACKS
        return [m for m in recorded
                if m.get("type") == "listen"
                and m["action"] not in STATE_SYNC_CALLBACKS]

    def test_on_callback_replayed(self):
        s = _make_session()
        W = s.get_widgets()
        btn = W.Button("click")
        handler = lambda: None
        btn.on("activated", handler)

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        listens = self._user_listens(s._recorded)
        assert len(listens) == 1
        assert listens[0]["wid"] == btn.wid
        assert listens[0]["action"] == "activated"

    def test_add_callback_replayed(self):
        s = _make_session()
        W = s.get_widgets()
        btn = W.Button("click")
        handler = lambda w: None
        btn.add_callback("activated", handler)

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        listens = self._user_listens(s._recorded)
        assert len(listens) == 1

    def test_multiple_callbacks_replayed(self):
        s = _make_session()
        W = s.get_widgets()
        btn = W.Button("click")
        btn.on("activated", lambda: None)
        btn.on("enter-notify", lambda: None)

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        listens = self._user_listens(s._recorded)
        assert len(listens) == 2
        actions = {l["action"] for l in listens}
        assert "activated" in actions
        assert "enter-notify" in actions

    def test_auto_sync_listeners_replayed(self):
        """Auto-sync listeners (move, resize) are re-registered for TopLevel."""
        s = _make_session()
        W = s.get_widgets()
        top = W.TopLevel(title="Test", resizable=True)

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        listens = [m for m in s._recorded if m.get("type") == "listen"]
        actions = {l["action"] for l in listens}
        assert "move" in actions
        assert "resize" in actions

    def test_auto_sync_resize_not_on_plain_widget(self):
        """Resize auto-sync only on widgets with resizable option."""
        s = _make_session()
        W = s.get_widgets()
        btn = W.Button("click")
        assert "resize" not in btn._auto_sync_actions


class TestReconstructMessageOrder:
    """Test that messages are sent in the correct order."""

    def test_create_before_state(self):
        s = _make_session()
        W = s.get_widgets()
        label = W.Label("hello")
        label.set_text("world")

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        # Find indices
        create_idx = next(
            i for i, m in enumerate(s._recorded)
            if m.get("type") == "create" and m["wid"] == label.wid)
        call_idx = next(
            i for i, m in enumerate(s._recorded)
            if m.get("type") == "call" and m.get("method") == "set_text")
        assert create_idx < call_idx

    def test_create_before_attach(self):
        s = _make_session()
        W = s.get_widgets()
        vbox = W.VBox()
        btn = W.Button("click")
        vbox.add_widget(btn, 0)

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        btn_create_idx = next(
            i for i, m in enumerate(s._recorded)
            if m.get("type") == "create" and m["wid"] == btn.wid)
        attach_idx = next(
            i for i, m in enumerate(s._recorded)
            if m.get("type") == "call" and m.get("method") == "add_widget")
        assert btn_create_idx < attach_idx

    def test_parent_created_before_child(self):
        s = _make_session()
        W = s.get_widgets()
        vbox = W.VBox()
        btn = W.Button("click")
        vbox.add_widget(btn, 0)

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        creates = [m for m in s._recorded if m.get("type") == "create"]
        vbox_idx = next(
            i for i, m in enumerate(creates) if m["wid"] == vbox.wid)
        btn_idx = next(
            i for i, m in enumerate(creates) if m["wid"] == btn.wid)
        assert vbox_idx < btn_idx


class TestReconstructEmpty:
    """Test reconstruction edge cases."""

    def test_empty_session(self):
        s = _make_session()
        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        # Only the bracket messages
        assert len(s._recorded) == 2
        assert s._recorded[0]["type"] == "reconstruct-start"
        assert s._recorded[1]["type"] == "reconstruct-end"

    def test_widget_no_state_changes(self):
        s = _make_session()
        W = s.get_widgets()
        W.VBox()  # container with no children or state

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        creates = [m for m in s._recorded if m.get("type") == "create"]
        assert len(creates) == 1
        # No state calls expected
        calls = [m for m in s._recorded if m.get("type") == "call"]
        assert len(calls) == 0

    def test_reconstruct_brackets(self):
        """reconstruct sends start/end bracket messages."""
        s = _make_session()
        W = s.get_widgets()
        W.Label("hi")

        s.start_recording()
        s.reconstruct()
        s.stop_recording()

        assert s._recorded[0]["type"] == "reconstruct-start"
        assert s._recorded[-1]["type"] == "reconstruct-end"
