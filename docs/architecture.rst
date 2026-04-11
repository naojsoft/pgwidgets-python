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

- ``{"type": "init", "id": 0}`` -- reset the browser to a clean slate.
- ``{"type": "create", "wid": 1, "class": "Button", "args": ["Click"]}`` --
  create a widget.
- ``{"type": "call", "wid": 1, "method": "set_text", "args": ["New"]}`` --
  call a method on a widget.
- ``{"type": "listen", "wid": 1, "action": "activated"}`` -- subscribe to a
  callback.
- ``{"type": "unlisten", "wid": 1, "action": "activated"}`` -- unsubscribe.

**Browser -> Python:**

- ``{"type": "result", "id": 1, "value": ...}`` -- method return value.
- ``{"type": "error", "id": 1, "error": "..."}`` -- method error.
- ``{"type": "callback", "wid": 1, "action": "activated", "args": [...]}`` --
  user interaction.
- ``{"type": "file-chunk", ...}`` -- chunked file data (see :doc:`callbacks`).

Session Model
-------------

Each browser tab that connects gets its own ``Session`` object. The session
owns:

- A widget map (``wid`` -> Python widget wrapper)
- A callback registry (``"wid:action"`` -> handler function)
- A message-ID counter for request/response matching

Multiple sessions can be active concurrently (controlled by ``max_sessions``).

Lifecycle:

1. Browser opens the URL and loads ``remote.html``.
2. JavaScript connects to the WebSocket server.
3. Python sends ``init``; browser acknowledges.
4. ``on_connect`` callback fires with the new ``Session``.
5. User code creates widgets, registers callbacks.
6. When the browser tab closes, ``on_disconnect`` fires and the session is
   cleaned up.

Widget References
-----------------

Widgets are identified by integer IDs (``wid``). When a Python widget is
passed as an argument to another widget's method (e.g., ``vbox.add_widget(btn,
0)``), the framework automatically converts the Python ``Widget`` object to a
``{"__wid__": N}`` reference on the wire, and converts it back on return
values.
