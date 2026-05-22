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
from pathlib import Path

from flask import Flask, render_template_string, request

# Make the sibling user_app.py importable regardless of the
# directory ``server.py`` is launched from.  multiprocessing.spawn
# (the macOS / Windows default) re-imports the target's module in
# the child process, so the path must already be set up before
# Process.start() is called.
sys.path.insert(0, str(Path(__file__).parent))

from user_app import build_app   # noqa: E402  (import after sys.path tweak)


# -- Flask boilerplate -----------------------------------------------

app = Flask(__name__)
log = logging.getLogger("flask-demo.server")

# Bind interface for both Flask and the per-visitor WebSocket
# children.  Set by main() from --host; module-level default so
# ``flask run server`` / WSGI runners still work without CLI args.
_BIND_HOST = "127.0.0.1"

# Loaded HTML template — embeds the per-visitor WebSocket URL.  Uses
# the published pgwidgets-js bundle from jsdelivr so the demo has no
# build step.  Replace the import-map URL with a local path if you
# need to run offline or test against a working-copy of pgwidgets-js.
HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>pgwidgets demo</title>
  <link rel="stylesheet"
        href="https://cdn.jsdelivr.net/npm/pgwidgets/Widgets.css">
  <script type="importmap">
    {"imports": {
        "pgwidgets": "https://cdn.jsdelivr.net/npm/pgwidgets/Widgets.js"
    }}
  </script>
  <style>body { margin: 0; }</style>
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
# want a tidy registry for shutdown).  Production code should also
# reap idle children based on whether their pgwidgets Application
# has any live connections.
_children = []


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
    """
    comm_queue = multiprocessing.Queue()
    child = multiprocessing.Process(
        target=build_app, args=(comm_queue, _BIND_HOST), daemon=True,
        name="pgwidgets-app",
    )
    child.start()
    _children.append(child)

    try:
        ws_port = comm_queue.get(timeout=5.0)
    except _queue_mod.Empty:
        log.error("child pid=%d did not report its port within timeout",
                  child.pid)
        return ("pgwidgets app process failed to start.  "
                "Check the server log.", 503)

    # Extract hostname portion of the Host header (e.g.
    # "example.com:5000" -> "example.com").  rsplit handles literal
    # IPv4 + port; IPv6 hosts (``[::1]:5000``) aren't preserved here
    # — extend with urllib.parse.urlsplit if you need them.
    ws_host = request.host.rsplit(":", 1)[0] if ":" in request.host \
        else request.host

    log.info("child pid=%d bound on %s:%d, browser will connect to %s:%d",
             child.pid, _BIND_HOST, ws_port, ws_host, ws_port)
    return render_template_string(HTML_TEMPLATE,
                                  ws_host=ws_host, ws_port=ws_port)


@app.route("/favicon.ico")
def favicon():
    """Return an empty 204 so the browser stops 404-ing on every page."""
    return ("", 204)


def _shutdown_children():
    """Best-effort cleanup of spawned children on Flask exit."""
    for p in _children:
        if p.is_alive():
            p.terminate()


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
