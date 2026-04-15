Architecture
============

Overview
--------

pgwidgets follows a client-server architecture. Python is the server; the
browser is the client. Widget constructors and method calls in Python are
translated to JSON messages and sent over WebSocket to the browser, where the
pgwidgets JavaScript library executes them. User interactions (clicks, input,
etc.) travel back as callback messages.

::

   Python (server)                     Browser (client)
   +-----------------+                 +------------------+
   | Application     |   WebSocket    | pgwidgets JS     |
   |   Session  <----|----JSON------->|   widget tree     |
   |     widgets     |                |   DOM rendering   |
   +-----------------+                +------------------+
          |
          | HTTP (static files)
          v
   JS/CSS assets served to browser

Servers
-------

The ``Application`` class starts two servers:

**HTTP server** (default port 9501)
   Serves the pgwidgets JavaScript/CSS assets and a connector HTML page.
   When a browser hits ``/``, it gets ``remote.html`` with the WebSocket URL
   injected. Set ``http_server=False`` if you serve the static files from
   your own web server (Flask, FastAPI, nginx, etc.).

**WebSocket server** (default port 9500)
   Carries the JSON command protocol. Each browser tab opens one WebSocket
   connection, which becomes one ``Session``.

JSON Protocol
-------------

All messages are JSON objects with a ``type`` field.

**Python -> Browser:**

- ``{"type": "init", "id": 0}`` -- handshake initiation.
- ``{"type": "session-info", "session_id": 1, "token": "..."}`` --
  session credentials for reconnection.
- ``{"type": "create", "wid": 1, "class": "Button", "args": ["Click"]}`` --
  create a widget.
- ``{"type": "call", "wid": 1, "method": "set_text", "args": ["New"]}`` --
  call a method on a widget.
- ``{"type": "call", ..., "silent": true}`` -- call a method without
  triggering callbacks (used for cross-browser sync).
- ``{"type": "listen", "wid": 1, "action": "activated"}`` -- subscribe to a
  callback.
- ``{"type": "unlisten", "wid": 1, "action": "activated"}`` -- unsubscribe.
- ``{"type": "reconstruct-start", "next_wid": N}`` -- begin UI reconstruction.
- ``{"type": "reconstruct-end"}`` -- end UI reconstruction.

**Browser -> Python:**

- ``{"type": "ack", "session_id": 1, "token": "..."}`` -- handshake
  acknowledgment (includes session credentials when reconnecting).
- ``{"type": "result", "id": 1, "value": ...}`` -- method return value.
- ``{"type": "error", "id": 1, "error": "..."}`` -- method error.
- ``{"type": "callback", "wid": 1, "action": "activated", "args": [...]}`` --
  user interaction.
- ``{"type": "file-chunk", ...}`` -- chunked file data (see :doc:`callbacks`).

Session Model
-------------

Each browser connection gets a ``Session`` object. Sessions persist
independently of browser connections -- they survive page refreshes,
network drops, and tab closes. Python is the source of truth for all
widget state.

A session owns:

- A widget tree with full state tracking (text, colors, sizes, children, etc.)
- A callback registry (``"wid:action"`` -> handler function)
- A list of active browser connections
- A security token for reconnection
- A message-ID counter for request/response matching

Multiple sessions can be active concurrently (controlled by ``max_sessions``).

Lifecycle:

1. Browser opens the URL and loads ``remote.html``.
2. JavaScript connects to the WebSocket server.
3. Python sends ``init``; browser acknowledges with session info (if reconnecting).
4. For a **new** connection: ``on_connect`` fires with a new ``Session``.
5. For a **reconnection**: the existing session's UI is automatically
   reconstructed in the browser.
6. User code creates widgets, registers callbacks.
7. When a browser disconnects, ``on_disconnect`` fires. The session
   remains alive for reconnection.
8. Sessions are only destroyed when ``session.destroy()`` is called explicitly.

Reconnection and Reconstruction
--------------------------------

When a browser reconnects to an existing session (e.g. after a page refresh),
the framework walks the widget tree and replays every widget's creation,
state, children, and callbacks. The browser receives the full UI as if it
were being built for the first time.

The reconstruction process:

1. Clean up stale auto-wrapped widget references from the previous connection.
2. Send ``reconstruct-start`` so the browser suppresses callback echo.
3. For each widget (parents before children):

   a. Create the widget with its original constructor arguments.
   b. Replay item lists (e.g. ComboBox items).
   c. Replay state changes (text, colors, size, position, etc.).
   d. Attach to parent via the same child method used originally.
   e. Replay factory calls (menu actions, toolbar actions, separators).
   f. Re-register all callbacks.
   g. Re-register auto-sync listeners.

4. Replay deferred state (splitter sizes, tab/stack index, tree collapse state).
5. Replay show/hide state.
6. Send ``reconstruct-end``.

Multi-Browser Synchronization
-----------------------------

Multiple browsers can connect to the same session simultaneously. When one
browser triggers a state change (slider move, tab switch, tree expand, etc.),
the change is pushed to all other connected browsers in real time.

::

   Browser A                Python (session)              Browser B
   +---------+              +---------------+              +---------+
   | slider  |---callback-->| update state  |---push------>| slider  |
   | moved   |              | in _state     |  (silent)    | updated |
   +---------+              +---------------+              +---------+

The push uses a ``silent`` flag so the receiving browser suppresses callback
echo, preventing infinite feedback loops.

State changes that are synchronized include:

- Widget state: slider values, checkbox state, text content, tab index, etc.
- Layout: move and resize of windows and MDI subwindows.
- Tree/table: expand, collapse, and sort operations.
- Child management: closing MDI subwindows or tab pages.

Headless Sessions
-----------------

Sessions can be created without a browser using
``app.create_session()``. The widget tree can be built up before any
browser connects. When a browser navigates to the session URL, the
pre-built UI is reconstructed automatically.

.. code-block:: python

   session = app.create_session()
   Widgets = session.get_widgets()
   top = Widgets.TopLevel(title="Pre-built UI")
   top.show()
   # ... build the full UI ...
   # When a browser connects with this session's ID and token,
   # the UI appears immediately.

Widget References
-----------------

Widgets are identified by integer IDs (``wid``). When a Python widget is
passed as an argument to another widget's method (e.g., ``vbox.add_widget(btn,
0)``), the framework automatically converts the Python ``Widget`` object to a
``{"__wid__": N}`` reference on the wire, and converts it back on return
values.
