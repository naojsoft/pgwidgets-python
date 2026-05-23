# Flask multi-process pgwidgets demo

One pgwidgets `Application` per visitor, each in a fresh OS process
with its own WebSocket port.  Returning visitors (refresh, bookmark,
second tab pointed at the same URL) are routed back to their
original process so pgwidgets-python's session-reconstruct path can
bring the UI back exactly where it was.

- **`server.py`** — Flask front-end.  For each new visitor, spawns
  a child process running a fresh `Application` and returns an HTML
  page whose `RemoteInterface` connects to that child's WebSocket
  port.  Keeps a `(session_id, token) → (port, process)` registry
  so subsequent visits carrying matching credentials in the URL
  re-attach to the existing child instead of spawning a new one.
- **`user_app.py`** — The per-visitor `Application` definition.
  Subclass `PGFlaskApp` and override `build_gui(session)` to build
  your UI; the surrounding machinery (socket binding, idle-grace
  self-shutdown, reporting credentials back to the parent) stays
  the same.  The child itself binds an ephemeral TCP socket and
  hands it directly to `Application(ws_sock=...)` — the port is
  held continuously, no TOCTOU race with another process.  Can
  also be run standalone (`python user_app.py`) for quick UI
  debugging without Flask in the loop; the port is auto-allocated
  and logged.

## Run

```
pip install Flask pgwidgets-python pgwidgets-js
python server.py
# browse to http://localhost:5000/
```

A *new* visitor (no credentials on the URL) triggers a brand-new
process.  A *returning* visitor whose URL still carries
`?session=N&token=ABC` from a previous visit is routed back to the
existing child for that session, if it's still alive — so a
refresh, a bookmark, or a second tab opened to the same URL all
re-attach to the same Application, and pgwidgets-python's session-
reconstruct path can restore the UI to where it was left.

When the last browser closes (or navigates away), the child waits
a grace period — `IDLE_GRACE_SECONDS` in `user_app.py`, default
5 minutes — to absorb page refreshes, brief network drops, and
the user closing/reopening a laptop, then exits.  A reconnect
within the grace window cancels the pending shutdown.

### Session routing

The parent keeps a `(session_id, token) → (ws_port, process)`
registry.  The wire protocol between parent and child is a single
tagged message:

```
("ready", ws_port, session_id, token)
```

sent by the child once, **before** `app.run()` blocks.  The child
pre-creates a session via `Application.create_session()` and
builds the UI on it before any browser arrives — so by the time
the parent responds to the visitor, the credentials are already
known and the UI is already constructed.  The HTTP handler
embeds those credentials in the HTML response (via an inline
`history.replaceState` that runs before the pgwidgets-js module
script) so the browser's WebSocket handshake lands directly on
the pre-built session and pgwidgets-python's reconstruct path
replays the state.

`/` flow:

- credentials present in the URL (a refresh / bookmark / shared
  link) **and** match an alive child → render HTML pointed at the
  existing child;
- credentials missing → spawn a new child, read its `ready`
  message, register `(session_id, token) → (port, process)`, and
  render HTML that embeds those credentials onto the URL so the
  next handshake re-attaches.

The registry is opportunistically cleaned along with the child-
reaper (any entry whose `Process` is no longer alive is dropped),
so dead-child credentials don't linger.

### Why pre-create the session

Two reasons:

1. **One round-trip.**  Without prewarm, the child has no
   credentials until the first browser handshake (where
   `_ws_handler` creates the session), so the parent can't embed
   them in the HTML.  You'd either redirect (`302 → /?session=…`)
   or wait for the credentials before responding.  Prewarm makes
   the credentials known synchronously at spawn time.
2. **State preserved across the first refresh.**  Once the
   credentials are baked onto the URL, a refresh lands the
   browser on the *same* Application; `do_reconstruct` replays
   whatever the UI has accumulated by then.  Without prewarm, the
   first visit creates a session lazily and the credentials only
   appear on the URL *after* the WebSocket has shaken hands —
   leaving a small window where a very fast refresh would have
   spawned a fresh process.

### Try it (verify the reconnect path)

1. Browse to `http://localhost:5000/`.  The URL bar immediately
   updates to include `?session=…&token=…` — that's the inline
   `replaceState` baking the pre-warmed session's credentials
   onto the URL before the pgwidgets-js module loads.
2. Interact with the demo UI (click the button so the label
   changes to "Clicked!", say).
3. **Refresh the tab.**  The label should still say "Clicked!" —
   you've landed on the *same* Application process, and its
   session reconstruct path has rebuilt the UI exactly where it
   was.  Confirm in DevTools → Network → WS that the WebSocket
   URL's port is unchanged.
4. Open the same URL (with the session/token query) in a *second*
   tab.  It joins the same Application — clicking the button in
   either tab updates the label in both (multi-browser sync).

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
- **Trust model for the routing token.** The registry trusts the
  `token` URL query parameter as proof of session identity — the
  same threat model pgwidgets-python's `_ws_handler` uses for
  WebSocket-level reconnect.  Anyone who can read a session URL
  can re-attach to that session.  Tokens are randomly generated
  and long enough that guessing is impractical, but URL theft
  (shared link, browser-history snoop, server log) lets the
  thief in.  Don't expose this demo unmodified on the open
  internet without thinking through how URLs leak in your
  context.
- **Reaper is request-driven, not periodic.** A child that has
  self-terminated after the idle grace will sit as a zombie until
  the next `/` request triggers `_reap_dead_children()`.  Fine for
  a demo; for an idle production server you'd add a periodic
  background reaper (e.g. a `threading.Timer` chain).
- **Single-message-per-tag protocol.** The child sends `("port", …)`
  once and `("creds", …)` once.  If you extend the demo to update
  state in the parent over time, switch to a clear schema and
  document it (and consider replacing the `Queue` with a `Pipe` or
  a small RPC layer).
