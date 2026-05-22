# Flask multi-process pgwidgets demo

One pgwidgets `Application` per visitor, each in a fresh OS process
with its own WebSocket port.

- **`server.py`** — Flask front-end.  Each request to `/` spawns a
  child process running a fresh `Application`, waits for the child
  to report its WebSocket port through a `multiprocessing.Queue`,
  then returns an HTML page whose `RemoteInterface` connects back
  to it.
- **`user_app.py`** — The per-visitor `Application` definition.
  The child itself binds an ephemeral TCP socket, hands it directly
  to `Application(ws_sock=...)` (so the port is held continuously —
  no race with another process), and reports the resulting port
  back through the queue.  Edit the body of `setup(session)` to
  build your UI.  Can also be run standalone (`python user_app.py`)
  for quick UI debugging without Flask in the loop; the port is
  auto-allocated and logged.

## Run

```
pip install Flask pgwidgets-python pgwidgets-js
python server.py
# browse to http://localhost:5000/
```

Every browser tab triggers a brand-new process.  When the tab is
closed (or the browser navigates away), the child waits a grace
period — `IDLE_GRACE_SECONDS` in `user_app.py`, default 5 minutes —
to absorb page refreshes, brief network drops, and the user
closing/reopening a laptop, then exits.  Reconnecting within the
grace window cancels the pending shutdown.

### Listening on other interfaces

By default Flask and each per-visitor WebSocket bind to
``127.0.0.1`` (loopback only).  To accept connections from other
machines:

```
python server.py --host 0.0.0.0 --port 8080
```

The bind interface and the WebSocket URL are decoupled — the
browser is given a ``ws://`` URL derived from the same hostname it
used to reach Flask, so the same server can be reached via
``localhost``, by IP address, or by DNS name with no further
configuration.

## What the browser loads

Each HTML response embeds the per-visitor WebSocket URL.  The
pgwidgets-js bundle (`Widgets.js`, `Widgets.css`, the `modules/`
subtree, icons) is served by Flask itself, from the pip-installed
`pgwidgets-js` Python package — `pgwidgets_js.get_static_path()`
returns the directory and a `/pgwidgets-js/<path>` route in
`server.py` exposes it.  No CDN, no network dependency at runtime,
and the version on the wire always matches the one in your venv.

To point at an in-progress working copy of pgwidgets-js instead of
the installed package, either ``pip install -e .`` from the
pgwidgets-js source tree (so `get_static_path()` resolves to the
working copy), or replace `PGWIDGETS_JS_ROOT` in `server.py` with
a hard path to that tree's `static/` directory.

## Caveats

- **Flask debug mode is off.** The reloader spawns a second
  process, which combined with `multiprocessing` can produce
  surprising behavior on Windows / macOS.  Restart `server.py` by
  hand after edits.
