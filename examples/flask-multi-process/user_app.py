"""Per-visitor pgwidgets Application.

This module exposes a single function, :func:`build_app`, that runs
a fresh pgwidgets :class:`Application` on a given WebSocket port.
The Flask server in ``server.py`` spawns one such process for every
incoming request, so each visitor gets isolated widget state.

Customize the body of ``setup(session)`` below to build whatever
UI your demo needs — everything from ``app.on_connect`` downwards
mirrors the canonical "Hello, pgwidgets" example in the docs, just
with the WebSocket port supplied by the caller instead of being
hard-coded.
"""

import logging
import os
import socket
import threading

from pgwidgets.sync.application import Application


# Idle grace period before a per-visitor child self-terminates after
# its last browser connection has gone away.  Long enough to cover
# page refreshes, network blips, and a user briefly closing their
# laptop; short enough that accidentally-abandoned tabs don't leak
# processes forever.  Tune to taste.
IDLE_GRACE_SECONDS = 5 * 60


def build_app(comm_queue=None, host="127.0.0.1"):
    """Bind a free port and run a fresh pgwidgets Application on it.

    Picks the port inside this process (never released before
    handing it to ``Application``), so there is no TOCTOU race with
    any other process for the chosen port number.

    Parameters
    ----------
    comm_queue : multiprocessing.Queue or None
        Channel back to the parent process.  Two tagged messages are
        sent through it during normal operation:

        * ``("port", ws_port)`` — sent once at startup, as soon as
          the WebSocket socket is bound.  The parent reads this
          synchronously to embed the per-visitor URL in its HTML
          response.
        * ``("creds", session_id, token)`` — sent once when the
          first browser connects, so the parent can index this
          child in a ``(session_id, token) -> port`` registry and
          route future visitors arriving with matching credentials
          back to this very child (instead of spawning a new one).

    host : str
        Interface to bind the WebSocket listener on.  ``"127.0.0.1"``
        for loopback-only, ``"0.0.0.0"`` for all interfaces, or any
        specific NIC IP.  Browsers reach the WebSocket via whatever
        hostname Flask reports to them, which is independent of the
        bind interface used here.

    Blocks until the parent process kills the child (or the
    interpreter exits).
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [pid %(process)d] "
               "%(levelname)s %(name)s: %(message)s",
    )
    logger = logging.getLogger("flask-demo.app")

    pg_app = PGFlaskApp(logger, host, comm_queue=comm_queue)
    pg_app.build_app()
    pg_app.run()


class PGFlaskApp:
    """Subclass this and override build_gui()"""

    def __init__(self, logger, host, comm_queue=None):
        self.logger = logger
        self.host = host
        self.comm_queue = comm_queue

        self.grace_lock = threading.Lock()
        self.grace_timer = None
        self.session = None
        self.sock = None
        self.idle_grace_seconds = IDLE_GRACE_SECONDS

    def build_app(self):
        # Bind a TCP socket on an ephemeral port.  This socket is then
        # handed to Application via ``ws_sock=``, which forwards it to
        # the underlying websockets server — the port is never released
        # between "find" and "bind", so no other process can grab it.
        # AF_INET6 with V6ONLY=0 would be nicer (dual-stack), but for a
        # demo the AF_INET path covers most use cases.
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock = sock
        sock.setblocking(False)
        sock.bind((self.host, 0))
        sock.listen()
        self.ws_port = sock.getsockname()[1]
        self.logger.info("starting Application on ws://%s:%d", self.host,
                         self.ws_port)
        if self.comm_queue is not None:
            # Tagged so the parent's reader can dispatch on
            # message type — see build_app's docstring for the
            # protocol.
            self.comm_queue.put(("port", self.ws_port))

        self.app = Application(
            host=self.host,
            ws_sock=self.sock,        # adopt the already-bound socket
            http_server=False,        # Flask serves the HTML.
        )
        self.app.on_connect(self.connect_cb)
        self.app.on_disconnect(self.disconnect_cb)
        return self.app

    def run(self):
        self.app.run()

    # Idle-grace machinery.  When the last browser connection drops
    # we start a timer; if a reconnect arrives before it fires (e.g.
    # the browser auto-reconnecting after a network blip, or the
    # user re-opening a tab to the same URL), it gets cancelled.
    # Otherwise the timer calls os._exit(0) to terminate this whole
    # child process — the cleanup the Flask demo wants since each
    # visitor has their own process and there's no other reason to
    # keep an idle one alive.
    #
    # This is opt-in and demo-specific.  pgwidgets-python's default
    # behaviour is to keep sessions alive across disconnects (so a
    # user can refresh and find their UI exactly where they left
    # it), which is the right behaviour for a long-running single-
    # Application server.
    #
    # The hookup is more subtle than it looks: ``app.on_connect``
    # only fires for *session creation*; subsequent WebSocket
    # reconnects to the same session take the ``do_reconstruct``
    # path inside Application and bypass on_connect entirely.  If
    # we only cancelled on on_connect, the very common case "browser
    # auto-reconnects after a transient drop" would let the timer
    # fire anyway and kill the live session.  So we *also* hook
    # ``session.add_connection``, which IS called for every WS
    # attachment.

    def cancel_grace(self):
        with self.grace_lock:
            t = self.grace_timer
            if t is not None:
                t.cancel()
                self.grace_timer = None
                self.logger.info("connection reestablished; grace timer cancelled")

    def start_grace(self):
        with self.grace_lock:
            if self.grace_timer is not None:
                return  # already armed
            self.logger.info("no browser connected; exiting in %ds if no reconnect",
                             self.idle_grace_seconds)
            t = threading.Timer(self.idle_grace_seconds, self._on_grace_expired)
            t.daemon = True
            t.start()
            self.grace_timer = t

    def _on_grace_expired(self):
        # Drop the timer reference first so future on_disconnect
        # events can arm a fresh timer if this one happens to be
        # a no-op (see below).
        with self.grace_lock:
            self.grace_timer = None
        # Defensive double-check: a reconnect could have arrived
        # between the timer being scheduled and it firing, racing
        # ahead of the cancel.  Don't kill the process if anyone is
        # actually connected.
        s = self.session
        if s is not None and s.is_connected:
            self.logger.info("reconnect detected as grace fired; not exiting")
            return
        self.logger.info("idle grace period elapsed, exiting child process")
        # os._exit bypasses Python cleanup; fine here because we're
        # a daemon child with no shared state and the OS reclaims
        # everything.  sys.exit() would only raise SystemExit on
        # this Timer thread, leaving the main asyncio loop alive.
        os._exit(0)

    def disconnect_cb(self, session):
        # ``on_disconnect`` fires *after* the connection is removed,
        # so ``is_connected`` reflects post-disconnect state.
        if not session.is_connected:
            self.start_grace()

    def connect_cb(self, session):
        self.session = session

        # Report this session's credentials to the parent so it can
        # route future ``/?session=...&token=...`` requests back to
        # this child instead of spawning a new process.  on_connect
        # only fires on session *creation*, which is exactly when
        # the credentials first become known and need to be
        # registered — subsequent WebSocket reconnections to the
        # same session bypass on_connect.
        if self.comm_queue is not None:
            try:
                self.comm_queue.put(
                    ("creds", session.id, session.token))
            except Exception as e:                 # pragma: no cover
                self.logger.warning(
                    "could not report session credentials: %s", e)

        self.cancel_grace()

        # ``on_connect`` only fires for session creation, so we
        # also wrap ``session.add_connection`` to cancel the grace
        # timer on subsequent WS reconnects to the same session
        # (browser auto-reconnect, second tab joining, ...).
        _orig_add = session.add_connection

        def _add_with_cancel(ws):
            self.cancel_grace()
            return _orig_add(ws)

        session.add_connection = _add_with_cancel

        self.build_gui(session)

    def build_gui(self, session):
        """This should build up and show your UI"""

        Widgets = session.get_widgets()

        # ---- start of user-editable area ------------------------
        # Replace everything between the markers with your own UI.

        top = Widgets.TopLevel(title="Hello", resizable=True)
        top.resize(400, 300)

        btn = Widgets.Button("Click me")
        label = Widgets.Label(f"Ready (ws port {self.ws_port})")

        btn.on("activated", lambda: label.set_text("Clicked!"))

        vbox = Widgets.VBox(spacing=8, padding=10)
        vbox.add_widget(btn, 0)
        vbox.add_widget(label, 1)
        top.set_widget(vbox)
        top.show()

        # ---- end of user-editable area --------------------------


if __name__ == "__main__":
    # Standalone smoke-test entry point.  Lets you run this file
    # on its own to debug the UI without the Flask front-end —
    # the port is allocated automatically and logged to stdout, so
    # check the log line ``starting Application on ws://...`` for
    # the URL to point your browser's remote.html at.
    build_app()
