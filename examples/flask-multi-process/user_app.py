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
        Channel back to the parent process.  One message is sent
        through it at startup, **before** ``app.run()`` blocks:

        * ``("ready", ws_port, session_id, token)``

        The child pre-creates a session (via
        :meth:`Application.create_session`) and builds the UI on
        it *before* any browser arrives — so by the time the parent
        responds to the visitor, the credentials are already known
        and the UI is already constructed.  The parent embeds the
        credentials in the HTML, the browser sends them on the
        WebSocket handshake, and pgwidgets-python's reconstruct
        path replays the pre-built state onto the browser.

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

        self.app = Application(
            host=self.host,
            ws_sock=self.sock,        # adopt the already-bound socket
            http_server=False,        # Flask serves the HTML.
        )
        # Disconnect callback wires up the idle-grace machinery.
        self.app.on_disconnect(self.disconnect_cb)

        # Pre-create the session, *before* any browser arrives, so
        # we can build the UI ahead of time and ship the
        # credentials to the parent in one shot.  When the browser
        # later connects with matching credentials, Application
        # takes the reconstruct path and the pre-built state is
        # replayed onto it.  on_connect does NOT fire in that
        # case — so we hook ``add_connection`` here (not in a
        # connect callback) to cancel the grace timer on every WS
        # attach.
        self.session = self.app.create_session()
        _orig_add = self.session.add_connection

        def _add_with_cancel(ws):
            self.cancel_grace()
            return _orig_add(ws)

        self.session.add_connection = _add_with_cancel

        # Arm the grace timer immediately.  Without this, a child
        # whose visitor never actually loads the HTML (or whose
        # browser fails to handshake) would sit idle forever — the
        # disconnect callback only fires after a connect, so it
        # wouldn't be enough.
        self.start_grace()

        # Tell the parent we're ready.  This single message
        # carries everything it needs to render the HTML response:
        # the WebSocket port, plus the credentials the browser
        # should present on its first handshake so it lands on
        # this pre-built session.
        if self.comm_queue is not None:
            self.comm_queue.put(
                ("ready", self.ws_port,
                 self.session.id, self.session.token))

        # Build the UI on the pre-created session.  By the time
        # the browser handshakes, this has already run and the
        # session's _state / _children / _registered_callbacks are
        # all populated — Application's reconstruct path replays
        # them to the browser.
        self.build_gui(self.session)

        return self.app

    def run(self):
        self.app.run()

    # Idle-grace machinery.  The timer arms in two situations:
    #
    #   1. At session creation (in build_app), so a child whose
    #      visitor never actually loads the HTML still exits
    #      eventually.
    #   2. Whenever the last browser connection drops, via the
    #      on_disconnect callback.
    #
    # The timer is cancelled by the ``session.add_connection``
    # wrapper installed in build_app, which fires for every WS
    # attach — both the initial connect and any reconnect.  This
    # matters because pre-warmed sessions (created via
    # ``app.create_session()`` before any browser arrives) take the
    # reconstruct path on browser handshake, bypassing on_connect
    # entirely; relying on on_connect for the cancel would miss
    # both that case and the browser-auto-reconnect-after-blip
    # case.
    #
    # When the timer expires, the child calls ``os._exit(0)`` —
    # the cleanup the Flask demo wants, since each visitor has
    # their own process and there's no other reason to keep an
    # idle one alive.
    #
    # This is opt-in and demo-specific.  pgwidgets-python's default
    # behaviour is to keep sessions alive across disconnects (so a
    # user can refresh and find their UI exactly where they left
    # it), which is the right behaviour for a long-running single-
    # Application server.

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
