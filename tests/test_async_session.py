"""
Tests for the async backend's session lifecycle.

``create_session`` is a plain (synchronous) method, so these tests need
no running event loop.  They mirror the auto-id / collision-safety tests
of the sync backend in ``test_session.py``.
"""

import logging
import threading

from pgwidgets.async_.application import Application


def _make_app(**kwargs):
    """Create an async Application without starting servers."""
    app = Application.__new__(Application)
    app._host = "127.0.0.1"
    app._ws_port = 9500
    app._http_port = 9501
    app._use_http_server = False
    app._concurrency = kwargs.get("concurrency", "concurrent")
    app._max_sessions = None
    app._sessions = {}
    app._next_session_id = 1
    app._on_connect = None
    app._on_disconnect = None
    app._widget_classes = {}

    logger = logging.getLogger("pgwidgets.test.async")
    logger.addHandler(logging.NullHandler())
    app._logger = logger

    return app


class TestAsyncSessionCreation:
    def test_create_session_auto_id(self):
        app = _make_app()
        s1 = app.create_session()
        s2 = app.create_session()
        assert s1.id == 1
        assert s2.id == 2

    def test_create_session_auto_id_skips_existing(self):
        # A default session is created with an explicit id, then more are
        # auto-allocated.  An auto-allocated id must not collide with /
        # silently overwrite the explicitly-created one.
        app = _make_app()
        default = app.create_session(session_id=1)
        extra = app.create_session()        # auto-allocated
        assert extra.id != default.id
        assert app._sessions[default.id] is default   # not overwritten
        assert app._sessions[extra.id] is extra

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
