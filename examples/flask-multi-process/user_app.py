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


def build_app(port_queue=None, host="127.0.0.1"):
    """Bind a free port and run a fresh pgwidgets Application on it.

    Picks the port inside this process (never released before
    handing it to ``Application``), so there is no TOCTOU race with
    any other process for the chosen port number.

    Parameters
    ----------
    port_queue : multiprocessing.Queue or None
        If given, the chosen port is reported back to the parent
        through it.  The Flask server in ``server.py`` uses that to
        embed the per-visitor WebSocket URL in its HTML response.
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
    log = logging.getLogger("flask-demo.app")

    # Bind a TCP socket on an ephemeral port.  This socket is then
    # handed to Application via ``ws_sock=``, which forwards it to
    # the underlying websockets server — the port is never released
    # between "find" and "bind", so no other process can grab it.
    # AF_INET6 with V6ONLY=0 would be nicer (dual-stack), but for a
    # demo the AF_INET path covers most use cases.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(False)
    sock.bind((host, 0))
    sock.listen()
    ws_port = sock.getsockname()[1]
    log.info("starting Application on ws://%s:%d", host, ws_port)
    if port_queue is not None:
        port_queue.put(ws_port)

    app = Application(
        host=host,
        ws_sock=sock,             # adopt the already-bound socket
        http_server=False,        # Flask serves the HTML.
    )

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
    grace_lock = threading.Lock()
    grace_timer = {"t": None}
    session_holder = {"s": None}

    def cancel_grace():
        with grace_lock:
            t = grace_timer["t"]
            if t is not None:
                t.cancel()
                grace_timer["t"] = None
                log.info("connection reestablished; grace timer cancelled")

    def start_grace():
        with grace_lock:
            if grace_timer["t"] is not None:
                return  # already armed
            log.info("no browser connected; exiting in %ds if no reconnect",
                     IDLE_GRACE_SECONDS)
            t = threading.Timer(IDLE_GRACE_SECONDS, _on_grace_expired)
            t.daemon = True
            t.start()
            grace_timer["t"] = t

    def _on_grace_expired():
        # Drop the timer reference first so future on_disconnect
        # events can arm a fresh timer if this one happens to be
        # a no-op (see below).
        with grace_lock:
            grace_timer["t"] = None
        # Defensive double-check: a reconnect could have arrived
        # between the timer being scheduled and it firing, racing
        # ahead of the cancel.  Don't kill the process if anyone is
        # actually connected.
        s = session_holder["s"]
        if s is not None and s.is_connected:
            log.info("reconnect detected as grace fired; not exiting")
            return
        log.info("idle grace period elapsed, exiting child process")
        # os._exit bypasses Python cleanup; fine here because we're
        # a daemon child with no shared state and the OS reclaims
        # everything.  sys.exit() would only raise SystemExit on
        # this Timer thread, leaving the main asyncio loop alive.
        os._exit(0)

    @app.on_disconnect
    def _on_disconnect(session):
        # ``on_disconnect`` fires *after* the connection is removed,
        # so ``is_connected`` reflects post-disconnect state.
        if not session.is_connected:
            start_grace()

    @app.on_connect
    def setup(session):
        session_holder["s"] = session
        cancel_grace()

        # ``on_connect`` only fires for session creation, so we
        # also wrap ``session.add_connection`` to cancel the grace
        # timer on subsequent WS reconnects to the same session
        # (browser auto-reconnect, second tab joining, …).
        _orig_add = session.add_connection

        def _add_with_cancel(ws):
            cancel_grace()
            return _orig_add(ws)

        session.add_connection = _add_with_cancel

        Widgets = session.get_widgets()

        # ---- start of user-editable area ------------------------
        # Replace everything between the markers with your own UI.

        top = Widgets.TopLevel(title="Hello", resizable=True)
        top.resize(400, 300)

        btn = Widgets.Button("Click me")
        label = Widgets.Label(f"Ready (ws port {ws_port})")

        btn.on("activated", lambda: label.set_text("Clicked!"))

        vbox = Widgets.VBox(spacing=8, padding=10)
        vbox.add_widget(btn, 0)
        vbox.add_widget(label, 1)
        top.set_widget(vbox)
        top.show()

        # ---- end of user-editable area --------------------------

    app.run()


if __name__ == "__main__":
    # Standalone smoke-test entry point.  Lets you run this file
    # on its own to debug the UI without the Flask front-end —
    # the port is allocated automatically and logged to stdout, so
    # check the log line ``starting Application on ws://...`` for
    # the URL to point your browser's remote.html at.
    build_app()
