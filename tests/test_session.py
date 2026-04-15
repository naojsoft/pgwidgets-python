"""
Tests for Phase 2: Session lifecycle.

Verifies that sessions can be created without a browser, have security
tokens, manage multiple connections, handle graceful no-connection
operation, and can be destroyed.
"""

import threading
from unittest.mock import MagicMock, AsyncMock

from pgwidgets.sync.application import Application, Session
from pgwidgets.sync.widget import Widget, build_widget_class
from pgwidgets.defs import WIDGETS


def _make_app(**kwargs):
    """Create an Application without starting servers."""
    app = Application.__new__(Application)
    app._host = "127.0.0.1"
    app._ws_port = 9500
    app._http_port = 9501
    app._use_http_server = False
    app._concurrency = kwargs.get("concurrency", "concurrent")
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
    app._widget_classes = {}

    import logging
    logger = logging.getLogger("pgwidgets.test")
    logger.addHandler(logging.NullHandler())
    app._logger = logger

    return app


class TestSessionCreation:
    """Test creating sessions without a browser."""

    def test_create_session_no_browser(self):
        app = _make_app()
        session = app.create_session()
        assert session is not None
        assert session.id == 1
        assert session.app is app

    def test_create_session_auto_id(self):
        app = _make_app()
        s1 = app.create_session()
        s2 = app.create_session()
        assert s1.id == 1
        assert s2.id == 2

    def test_create_session_explicit_id(self):
        app = _make_app()
        s = app.create_session(session_id="my-session")
        assert s.id == "my-session"

    def test_create_session_duplicate_id_raises(self):
        app = _make_app()
        app.create_session(session_id="dup")
        try:
            app.create_session(session_id="dup")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "dup" in str(e)

    def test_create_session_registered_in_app(self):
        app = _make_app()
        s = app.create_session()
        assert s.id in app._sessions
        assert app._sessions[s.id] is s

    def test_create_session_not_connected(self):
        app = _make_app()
        s = app.create_session()
        assert not s.is_connected
        assert s.connections == []


class TestSecurityToken:
    """Test that sessions have security tokens."""

    def test_session_has_token(self):
        app = _make_app()
        s = app.create_session()
        assert s.token is not None
        assert len(s.token) > 20

    def test_tokens_are_unique(self):
        app = _make_app()
        s1 = app.create_session()
        s2 = app.create_session()
        assert s1.token != s2.token

    def test_token_is_string(self):
        app = _make_app()
        s = app.create_session()
        assert isinstance(s.token, str)


class TestConnectionManagement:
    """Test add/remove connection."""

    def test_add_connection(self):
        app = _make_app()
        s = app.create_session()
        ws = MagicMock()
        s.add_connection(ws)
        assert s.is_connected
        assert len(s.connections) == 1

    def test_add_connection_no_duplicates(self):
        app = _make_app()
        s = app.create_session()
        ws = MagicMock()
        s.add_connection(ws)
        s.add_connection(ws)
        assert len(s._connections) == 1

    def test_remove_connection(self):
        app = _make_app()
        s = app.create_session()
        ws = MagicMock()
        s.add_connection(ws)
        s.remove_connection(ws)
        assert not s.is_connected
        assert s.connections == []

    def test_remove_nonexistent_connection(self):
        app = _make_app()
        s = app.create_session()
        ws = MagicMock()
        # Should not raise
        s.remove_connection(ws)

    def test_multiple_connections(self):
        app = _make_app()
        s = app.create_session()
        ws1 = MagicMock()
        ws2 = MagicMock()
        s.add_connection(ws1)
        s.add_connection(ws2)
        assert len(s.connections) == 2
        s.remove_connection(ws1)
        assert len(s.connections) == 1
        assert s.is_connected

    def test_session_with_initial_ws(self):
        app = _make_app()
        ws = MagicMock()
        s = Session(app, 1, ws=ws)
        assert s.is_connected
        assert len(s._connections) == 1

    def test_session_without_initial_ws(self):
        app = _make_app()
        s = Session(app, 1)
        assert not s.is_connected
        assert s._connections == []


class TestNoConnectionOperation:
    """Test that operations work gracefully without a browser."""

    def _make_session(self):
        app = _make_app()
        return app.create_session()

    def test_send_returns_none_no_connection(self):
        s = self._make_session()
        result = s._send({"type": "call", "wid": 1, "method": "test"})
        assert result is None

    def test_call_returns_none_no_connection(self):
        s = self._make_session()
        result = s._call(1, "set_text", "hello")
        assert result is None

    def test_create_returns_wid_no_connection(self):
        s = self._make_session()
        wid = s._create("Label")
        assert wid == 1

    def test_wid_increments_no_connection(self):
        s = self._make_session()
        wid1 = s._create("Label")
        wid2 = s._create("Button")
        assert wid1 == 1
        assert wid2 == 2

    def test_listen_stores_handler_no_connection(self):
        s = self._make_session()
        handler = lambda *args: None
        s._listen(1, "activated", handler)
        assert "1:activated" in s._callbacks
        assert s._callbacks["1:activated"] is handler

    def test_unlisten_removes_handler_no_connection(self):
        s = self._make_session()
        handler = lambda *args: None
        s._listen(1, "activated", handler)
        s._unlisten(1, "activated")
        assert "1:activated" not in s._callbacks


class TestSessionDestroy:
    """Test session destruction."""

    def test_destroy_removes_from_app(self):
        app = _make_app()
        s = app.create_session()
        sid = s.id
        assert sid in app._sessions
        s.destroy()
        assert sid not in app._sessions

    def test_destroy_multiple_sessions(self):
        app = _make_app()
        s1 = app.create_session()
        s2 = app.create_session()
        s1.destroy()
        assert s1.id not in app._sessions
        assert s2.id in app._sessions


class TestWidgetFactoryNoConnection:
    """Test that the widget factory works without a browser."""

    def _make_session_with_widgets(self):
        app = _make_app()
        from pgwidgets.sync.widget import build_all_widget_classes
        app._widget_classes = build_all_widget_classes()
        return app.create_session()

    def test_get_widgets_returns_namespace(self):
        s = self._make_session_with_widgets()
        W = s.get_widgets()
        assert hasattr(W, "Label")
        assert hasattr(W, "Button")

    def test_create_widget_no_connection(self):
        s = self._make_session_with_widgets()
        W = s.get_widgets()
        label = W.Label("hello")
        assert label is not None
        assert label.wid == 1
        assert label._state["text"] == "hello"

    def test_widget_state_tracking_no_connection(self):
        s = self._make_session_with_widgets()
        W = s.get_widgets()
        label = W.Label("hello")
        label.set_text("world")
        assert label.get_text() == "world"

    def test_widget_tree_no_connection(self):
        s = self._make_session_with_widgets()
        W = s.get_widgets()
        vbox = W.VBox()
        btn = W.Button("click")
        vbox.add_widget(btn, 0)
        assert btn._parent is vbox
        assert len(vbox._children) == 1

    def test_walk_widget_tree_no_connection(self):
        s = self._make_session_with_widgets()
        W = s.get_widgets()
        vbox = W.VBox()
        btn1 = W.Button("a")
        btn2 = W.Button("b")
        vbox.add_widget(btn1, 0)
        vbox.add_widget(btn2, 1)
        widgets = list(s.walk_widget_tree())
        assert vbox in widgets
        assert btn1 in widgets
        assert btn2 in widgets

    def test_callbacks_registered_no_connection(self):
        s = self._make_session_with_widgets()
        W = s.get_widgets()
        btn = W.Button("click")
        handler = lambda: None
        btn.on("activated", handler)
        assert "activated" in btn._registered_callbacks

    def test_root_widgets_tracked_no_connection(self):
        s = self._make_session_with_widgets()
        W = s.get_widgets()
        label = W.Label("a")
        btn = W.Button("b")
        assert label in s._root_widgets
        assert btn in s._root_widgets


class TestSessionRepr:
    """Test session string representation."""

    def test_repr(self):
        app = _make_app()
        s = app.create_session(session_id=42)
        assert repr(s) == "<Session id=42>"

    def test_repr_string_id(self):
        app = _make_app()
        s = app.create_session(session_id="my-session")
        assert repr(s) == "<Session id=my-session>"


class TestCallbackSuppression:
    """Test that callbacks are suppressed during reconstruction."""

    def test_reconstructing_flag_default_false(self):
        app = _make_app()
        s = app.create_session()
        assert s._reconstructing is False

    def test_dispatch_callback_suppressed_during_reconstruction(self):
        app = _make_app()
        s = app.create_session()
        # Register a handler
        called = []
        s._callbacks["1:activated"] = lambda wid, *args: called.append(True)
        # Should dispatch normally
        s._dispatch_callback(1, "activated")
        assert len(called) == 1

        # Should suppress during reconstruction
        s._reconstructing = True
        s._dispatch_callback(1, "activated")
        assert len(called) == 1  # not called again

        s._reconstructing = False
        s._dispatch_callback(1, "activated")
        assert len(called) == 2  # works again after reconstruction

    def test_reconstruct_sends_bracket_messages(self):
        """reconstruct() sends start/end and sets/clears the flag."""
        from pgwidgets.sync.widget import build_all_widget_classes
        app = _make_app()
        app._widget_classes = build_all_widget_classes()
        s = app.create_session()

        W = s.get_widgets()
        W.Label("hi")

        # Start tracking messages after widget creation
        messages = []

        def tracking_send(msg):
            messages.append(dict(msg))
            return {"type": "result", "value": None}

        s._send = tracking_send
        s.reconstruct()

        types = [m["type"] for m in messages]
        assert types[0] == "reconstruct-start"
        assert types[-1] == "reconstruct-end"
