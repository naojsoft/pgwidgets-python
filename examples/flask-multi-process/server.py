"""Flask + pgwidgets-python multi-process demo.

Each visitor to ``/`` is served a fresh pgwidgets Application
running in its own OS process with its own WebSocket port — so
sessions are fully isolated, and a slow handler in one session
can't block another.

Architecture::

    browser   ┌─────────────────────┐    HTTP /          ┌─────────────┐
       ──────▶│  Flask (port 5000)  │ ─────────────────▶│   user_app  │
              │  picks ws_port      │    spawn Process   │   process 1 │
              │  spawns child       │  ◀───────────── ws on 35211 ─────┘
              │  returns HTML       │                    ┌─────────────┐
              └─────────────────────┘                    │   user_app  │
                                                         │   process 2 │
              (one child per request)               ws on 41922 ────────┘

Run::

    pip install Flask pgwidgets-python
    python server.py
    # browse to http://localhost:5000/

Each browser tab triggers a fresh per-visitor process.
"""

import argparse
import logging
import multiprocessing
import queue as _queue_mod
import sys
import threading
from pathlib import Path

import pgwidgets_js
from flask import (Flask, render_template_string, request,
                   send_from_directory)

# Make the sibling user_app.py importable regardless of the
# directory ``server.py`` is launched from.  multiprocessing.spawn
# (the macOS / Windows default) re-imports the target's module in
# the child process, so the path must already be set up before
# Process.start() is called.
sys.path.insert(0, str(Path(__file__).parent))

from user_app import build_app   # noqa: E402  (import after sys.path tweak)

# Directory containing the bundled pgwidgets-js static assets
# (Widgets.js, Widgets.css, modules/, icons/, …).  Served from
# Flask so the page does not depend on a CDN being reachable.
PGWIDGETS_JS_ROOT = pgwidgets_js.get_static_path()


# -- Flask boilerplate -----------------------------------------------

app = Flask(__name__)
log = logging.getLogger("flask-demo.server")

# Bind interface for both Flask and the per-visitor WebSocket
# children.  Set by main() from --host; module-level default so
# ``flask run server`` / WSGI runners still work without CLI args.
_BIND_HOST = "127.0.0.1"

# Loaded HTML template — embeds the per-visitor WebSocket URL.
# pgwidgets-js is served from the local pip-installed package via
# the /pgwidgets-js/<path> route below, so the page doesn't depend
# on network access to a CDN and always matches whatever version
# of pgwidgets-js is pinned in your environment.
HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>pgwidgets demo</title>
  <link rel="stylesheet" href="/pgwidgets-js/Widgets.css">
  <script type="importmap">
    {"imports": {"pgwidgets": "/pgwidgets-js/Widgets.js"}}
  </script>
  <style>body { margin: 0; }</style>
  {% if embed_creds %}
  <script>
    // Bake the pre-warmed session credentials onto the URL before
    // the pgwidgets-js module reads them.  RemoteInterface looks
    // up ``?session=...&token=...`` in window.location.search at
    // construction time, so as long as this runs first the
    // browser will send the matching credentials on its WebSocket
    // handshake — and Application's reconstruct path will replay
    // the UI we already built onto it.  history.replaceState
    // doesn't trigger a navigation, so this is one round-trip.
    (function () {
        var params = new URLSearchParams(location.search);
        params.set("session", "{{ session_id }}");
        params.set("token", "{{ session_token }}");
        history.replaceState(null, "",
            location.pathname + "?" + params.toString() +
            (location.hash || ""));
    })();
  </script>
  {% endif %}
</head>
<body>
  <script type="module">
    import { Widgets } from "pgwidgets";
    new Widgets.RemoteInterface(Widgets, {
        url: "ws://{{ ws_host }}:{{ ws_port }}",
    });
  </script>
</body>
</html>
"""


# Keep references to spawned processes so they aren't garbage-
# collected (Process.__del__ doesn't kill the child, but we still
# want a tidy registry for shutdown).
_children = []
_children_lock = threading.Lock()

# Maps ``(session_id_str, token) -> (ws_port, Process)`` for every
# alive child whose pgwidgets Session has reported its credentials.
# Populated by per-child reader threads as ``("creds", sid, token)``
# messages arrive from the child's queue.  Consulted by ``/`` to
# route returning visitors back to their original process.
_registry = {}
_registry_lock = threading.Lock()


def _reap_dead_children():
    """Prune ``_children`` of any process that has exited, and drop
    the matching registry entries.

    Calling ``Process.is_alive()`` invokes ``waitpid(pid, WNOHANG)``
    under the hood, which collects the exit status of a dead child
    and lets the kernel free its process-table entry — so this
    doubles as a zombie reaper.

    Without this, children that self-terminate via the idle-grace
    timer in ``user_app.py`` would linger as defunct (Z) processes
    until Flask itself exits.  ``daemon=True`` only matters at
    parent shutdown; it does not reap exited children during normal
    operation.
    """
    with _children_lock:
        live = []
        for c in _children:
            if c.is_alive():
                live.append(c)
            else:
                # Belt-and-braces: explicit join with timeout=0 to
                # ensure the OS-level waitpid happens even if some
                # future Process implementation makes is_alive()
                # skip it.
                c.join(timeout=0)
        _children[:] = live
    with _registry_lock:
        stale = [k for k, (_p, c) in _registry.items()
                 if not c.is_alive()]
        for k in stale:
            del _registry[k]


def _derive_ws_host(req):
    """Extract the hostname portion of the Host header.

    rsplit handles literal IPv4 + port; IPv6 hosts
    (``[::1]:5000``) aren't preserved here — extend with
    urllib.parse.urlsplit if you need them.
    """
    if ":" in req.host:
        return req.host.rsplit(":", 1)[0]
    return req.host


@app.route("/")
def index():
    """Spawn a fresh per-visitor Application and return the HTML.

    Port allocation happens inside the child: it binds an ephemeral
    TCP socket, holds it, and reports the port back through a
    ``Queue``.  The bound socket is then handed straight to
    ``Application(ws_sock=…)``, so the port is never released
    between "discover" and "use" — no TOCTOU race with any other
    process.

    The WebSocket *bind* interface is whatever ``--host`` was set
    to (default 127.0.0.1).  The WebSocket *URL* given to the
    browser is derived from ``request.host`` — i.e. whichever
    hostname/IP the browser used to reach Flask — so the same
    server can be reached as ``localhost``, by IP, or by DNS name
    without configuration.

    Session-aware routing: if the request URL carries
    ``?session=N&token=ABC`` (the credentials pgwidgets-js writes
    onto the URL after the first connect) and a child is still
    alive serving that session, this handler returns HTML pointed
    at the **existing** child instead of spawning a new one.  That
    is how refreshes, bookmarks, and multi-tab sharing reach the
    same Application — and how pgwidgets-python's session
    reconstruct() path gets to do its job.
    """
    # Opportunistically reap any children that have self-terminated
    # via the idle-grace timer.  Without this they linger as
    # zombies until Flask exits (see ``_reap_dead_children``).
    _reap_dead_children()

    ws_host = _derive_ws_host(request)

    # ---- Try to re-attach to an existing session ----------------
    sid_q = request.args.get("session")
    token_q = request.args.get("token")
    if sid_q and token_q:
        with _registry_lock:
            entry = _registry.get((sid_q, token_q))
        if entry is not None:
            ws_port, child = entry
            if child.is_alive():
                log.info("re-attach session %s -> child pid=%d "
                         "on port %d (host %s)",
                         sid_q, child.pid, ws_port, ws_host)
                # Credentials are already on the URL; no need for
                # the inline replaceState block.
                return render_template_string(HTML_TEMPLATE,
                                              ws_host=ws_host,
                                              ws_port=ws_port,
                                              embed_creds=False,
                                              session_id=None,
                                              session_token=None)
            # Entry was stale — drop it and fall through to spawn.
            with _registry_lock:
                _registry.pop((sid_q, token_q), None)
            log.info("registry entry for session %s pointed at dead "
                     "child; spawning fresh process", sid_q)

    # ---- Spawn a fresh per-visitor child -----------------------
    #
    # The child pre-creates a session and builds its UI before
    # ``app.run()`` blocks, then reports
    # ``("ready", ws_port, session_id, token)`` over the queue.
    # We embed the credentials in the HTML response so the
    # browser's WebSocket handshake lands on the pre-built
    # session.
    comm_queue = multiprocessing.Queue()
    child = multiprocessing.Process(
        target=build_app, args=(comm_queue, _BIND_HOST), daemon=True,
        name="pgwidgets-app",
    )
    child.start()
    with _children_lock:
        _children.append(child)

    try:
        msg = comm_queue.get(timeout=5.0)
    except _queue_mod.Empty:
        log.error("child pid=%d did not signal ready within timeout",
                  child.pid)
        return ("pgwidgets app process failed to start.  "
                "Check the server log.", 503)

    if not (isinstance(msg, tuple) and len(msg) == 4
            and msg[0] == "ready"):
        log.error("unexpected startup message from child pid=%d: %r",
                  child.pid, msg)
        return ("Bad child startup response.", 503)

    _, ws_port, sid, token = msg
    ws_port = int(ws_port)

    # Register so future ``?session=...&token=...`` requests can
    # route back here.  Done synchronously, in the same handler,
    # so a refresh that arrives before this function returns can't
    # miss the entry.
    with _registry_lock:
        _registry[(str(sid), token)] = (ws_port, child)

    log.info("spawned child pid=%d bound on %s:%d for session %s; "
             "browser will connect to %s:%d",
             child.pid, _BIND_HOST, ws_port, sid, ws_host, ws_port)
    return render_template_string(HTML_TEMPLATE,
                                  ws_host=ws_host, ws_port=ws_port,
                                  embed_creds=True,
                                  session_id=sid,
                                  session_token=token)


@app.route("/pgwidgets-js/<path:filename>")
def pgwidgets_js_static(filename):
    """Serve pgwidgets-js's bundled static assets from the pip-
    installed copy.  The Widgets.js entry point uses relative imports
    (``./modules/Widget.js`` etc.), so the entire subtree has to be
    reachable under one URL prefix — ``send_from_directory`` handles
    that correctly out of the box."""
    return send_from_directory(PGWIDGETS_JS_ROOT, filename)


@app.route("/favicon.ico")
def favicon():
    """Return an empty 204 so the browser stops 404-ing on every page."""
    return ("", 204)


def _shutdown_children():
    """Best-effort cleanup of spawned children on Flask exit.

    ``daemon=True`` on each child already guarantees they will be
    terminated when this process exits, but ``terminate()``-ing
    explicitly here gives them a chance to be reaped (via the
    follow-on ``join``) so the process table is clean rather than
    relying on init to inherit them.
    """
    with _children_lock:
        for p in _children:
            if p.is_alive():
                p.terminate()
        for p in _children:
            p.join(timeout=1.0)
        _children.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Flask + pgwidgets-python multi-process demo.")
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Interface to bind both Flask and the per-visitor "
             "WebSocket children on.  Use 0.0.0.0 to accept "
             "connections from other machines, or a specific NIC IP "
             "to restrict to one interface.  (default: 127.0.0.1)")
    parser.add_argument(
        "--port", type=int, default=5000,
        help="HTTP port for Flask.  WebSocket ports are allocated "
             "ephemerally per visitor.  (default: 5000)")
    args = parser.parse_args()

    _BIND_HOST = args.host

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log.info("Flask serving on http://%s:%d  (WebSocket bind: %s)",
             args.host, args.port, args.host)

    # ``debug=False`` is important: Flask's reloader spawns two
    # processes (parent + reloader child) and that confuses
    # multiprocessing on some platforms.  For interactive editing,
    # restart the script manually.
    try:
        app.run(host=args.host, port=args.port, debug=False)
    finally:
        _shutdown_children()
