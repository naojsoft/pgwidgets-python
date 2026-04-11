"""
Asynchronous Application and Session classes.

Application — starts a WebSocket server and HTTP file server, manages
session lifecycle.

Session — one per browser connection, owns the widget tree and
callbacks for that connection.
"""

import asyncio
import json
import mimetypes
import traceback
from http.server import SimpleHTTPRequestHandler
from functools import partial
from pathlib import Path

import websockets

from pgwidgets_js import get_static_path, get_remote_html
from pgwidgets.defs import WIDGETS
from pgwidgets.async_.widget import Widget, build_all_widget_classes

_CONCURRENCY_MODES = ("serialized", "per_session", "concurrent")


class _Namespace:
    """Holds widget factory methods as attributes (W.Button, W.Label, etc.)."""
    pass


class Session:
    """
    A single browser connection with its own widget tree (async).

    Each browser tab that connects gets its own Session.  The session
    owns the widget map, callback registry, and message-ID counter for
    that connection.

    Parameters
    ----------
    app : Application
        The owning Application.
    ws : websockets.WebSocketServerProtocol
        The WebSocket connection for this session.
    session_id : int
        Unique session identifier.
    """

    def __init__(self, app, ws, session_id):
        self._app = app
        self._ws = ws
        self._id = session_id

        self._next_id = 1
        self._next_wid = 1
        self._pending = {}       # msg id -> Future
        self._callbacks = {}     # "wid:action" -> handler fn
        self._widget_map = {}    # wid -> Widget instance

        self._widget_classes = app._widget_classes
        self._transfers = {}     # transfer_id -> transfer state dict

        # Per-session lock (for "per_session" and "serialized" modes).
        self._cb_lock = None

    @property
    def id(self):
        """Unique session identifier."""
        return self._id

    @property
    def app(self):
        """The Application this session belongs to."""
        return self._app

    # -- Message handling --

    def _handle_message(self, data):
        msg = json.loads(data)
        if isinstance(msg, list):
            for m in msg:
                self._handle_one(m)
        else:
            self._handle_one(msg)

    def _handle_one(self, msg):
        msg_type = msg.get("type")

        if msg_type in ("result", "error"):
            msg_id = msg.get("id")
            future = self._pending.pop(msg_id, None)
            if future and not future.done():
                if msg_type == "error":
                    future.set_exception(RuntimeError(msg["error"]))
                else:
                    future.set_result(msg)

        elif msg_type == "file-chunk":
            self._handle_file_chunk(msg)

        elif msg_type == "callback":
            # If this is a drag-drop with a transfer_id, stash the
            # metadata — the real callback fires after all chunks arrive.
            if (msg.get("action") == "drag-drop"
                    and msg.get("args")
                    and isinstance(msg["args"][0], dict)
                    and "transfer_id" in msg["args"][0]):
                payload = msg["args"][0]
                tid = payload["transfer_id"]
                self._transfers[tid] = {
                    "wid": msg["wid"],
                    "payload": payload,
                    "file_data": {},   # file_index -> [chunk, ...]
                    "num_chunks": {},  # file_index -> expected count
                }
                return

            self._dispatch_callback(
                msg["wid"], msg["action"], *msg.get("args", []))

    def _handle_file_chunk(self, msg):
        """Handle a file-chunk message: buffer data and fire callbacks."""
        tid = msg["transfer_id"]
        transfer = self._transfers.get(tid)
        if transfer is None:
            return

        fi = msg["file_index"]
        fc = msg["file_count"]
        if fi not in transfer["file_data"]:
            transfer["file_data"][fi] = []
            transfer["num_chunks"][fi] = msg["num_chunks"]
        transfer["file_data"][fi].append(msg["data"])

        # Check if all files have received all their chunks.
        all_complete = (
            len(transfer["num_chunks"]) == fc
            and all(
                len(transfer["file_data"][i]) >= transfer["num_chunks"][i]
                for i in range(fc)
            )
        )

        # Compute byte-level progress from file sizes and chunk counts.
        files_meta = transfer["payload"]["files"]
        transferred_bytes = 0
        total_bytes = 0
        for i, fmeta in enumerate(files_meta):
            fsize = fmeta.get("size", 0)
            total_bytes += fsize
            nc = transfer["num_chunks"].get(i)
            if nc:
                received = len(transfer["file_data"].get(i, []))
                transferred_bytes += fsize * received // nc

        progress_info = {
            "transfer_id": tid,
            "file_index": fi,
            "chunk_index": msg["chunk_index"],
            "num_chunks": msg["num_chunks"],
            "transferred_bytes": transferred_bytes,
            "total_bytes": total_bytes,
            "complete": all_complete,
        }
        self._dispatch_callback(
            transfer["wid"], "drop-progress", progress_info)

        if all_complete:
            # Reassemble file data and fire drag-drop callback.
            payload = transfer["payload"]
            for i, file_meta in enumerate(payload["files"]):
                file_meta["data"] = "".join(
                    transfer["file_data"].get(i, []))
            del self._transfers[tid]
            self._dispatch_callback(
                transfer["wid"], "drag-drop", payload)

    def _dispatch_callback(self, wid, action, *args):
        """Dispatch a callback through the configured concurrency mode."""
        key = f"{wid}:{action}"
        handler = self._callbacks.get(key)
        if not handler:
            return
        cb_args = (wid, *args)
        mode = self._app._concurrency
        if mode == "concurrent":
            asyncio.ensure_future(handler(*cb_args))
        elif mode == "per_session":
            asyncio.ensure_future(
                self._serialized_dispatch(
                    handler, cb_args, self._cb_lock))
        else:  # serialized
            asyncio.ensure_future(
                self._serialized_dispatch(
                    handler, cb_args, self._app._cb_lock))

    @staticmethod
    async def _serialized_dispatch(handler, args, lock):
        """Run handler under a lock for serialized execution."""
        async with lock:
            try:
                result = handler(*args)
                if hasattr(result, "__await__"):
                    await result
            except Exception:
                traceback.print_exc()

    async def _send(self, msg):
        """Send a message and wait for the result."""
        msg_id = self._next_id
        self._next_id += 1
        msg["id"] = msg_id
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending[msg_id] = future
        await self._ws.send(json.dumps(msg))
        return await future

    def _alloc_wid(self):
        wid = self._next_wid
        self._next_wid += 1
        return wid

    # -- Low-level widget API --

    async def _create(self, js_class, *args):
        """Create a JS widget and return its wid."""
        wid = self._alloc_wid()
        resolved = [self._resolve_arg(a) for a in args]
        await self._send({
            "type": "create",
            "wid": wid,
            "class": js_class,
            "args": resolved,
        })
        return wid

    async def _call(self, wid, method, *args):
        """Call a method on a JS widget."""
        result = await self._send({
            "type": "call",
            "wid": wid,
            "method": method,
            "args": list(args),
        })
        return result.get("value")

    async def _listen(self, wid, action, handler):
        """Register a callback listener."""
        key = f"{wid}:{action}"
        self._callbacks[key] = handler
        await self._send({
            "type": "listen",
            "wid": wid,
            "action": action,
        })

    async def _unlisten(self, wid, action):
        """Remove a callback listener."""
        key = f"{wid}:{action}"
        self._callbacks.pop(key, None)
        await self._send({
            "type": "unlisten",
            "wid": wid,
            "action": action,
        })

    def _resolve_arg(self, arg):
        """Convert Widget instances to wire refs in outgoing args."""
        if isinstance(arg, Widget):
            return {"__wid__": arg.wid}
        if isinstance(arg, list):
            return [self._resolve_arg(a) for a in arg]
        if isinstance(arg, dict):
            return {k: self._resolve_arg(v) for k, v in arg.items()}
        return arg

    def _resolve_return(self, val):
        """Convert wire refs back to Widget instances in return values."""
        if isinstance(val, dict) and "__wid__" in val:
            wid = val["__wid__"]
            return self._widget_map.get(wid, val)
        if isinstance(val, list):
            return [self._resolve_return(v) for v in val]
        return val

    # -- Widget factory --

    def get_widgets(self):
        """Return a namespace with async factory methods for all widget types.

        Usage:
            Widgets = session.get_widgets()
            btn = await Widgets.Button("Click me")
        """
        ns = _Namespace()
        session = self

        for js_class, cls in self._widget_classes.items():
            defn = WIDGETS[js_class]

            def make_factory(js_cls, widget_cls, widget_defn):
                async def factory(*args, **kwargs):
                    pos_names = widget_defn.get("args", [])
                    opt_names = widget_defn.get("options", [])

                    js_args = list(args[:len(pos_names)])

                    for i, val in enumerate(args[len(pos_names):]):
                        if i < len(opt_names):
                            kwargs[opt_names[i]] = val

                    options = {}
                    for k in list(kwargs.keys()):
                        if k in opt_names:
                            options[k] = kwargs.pop(k)

                    if options:
                        js_args.append(options)

                    wid = await session._create(js_cls, *js_args)
                    widget = widget_cls(session, wid, js_cls)
                    session._widget_map[wid] = widget

                    for k, v in kwargs.items():
                        setter = f"set_{k}"
                        if hasattr(widget, setter):
                            await getattr(widget, setter)(v)
                        else:
                            raise TypeError(
                                f"{js_cls}() got unexpected keyword "
                                f"argument '{k}'")

                    return widget

                factory.__name__ = js_cls
                factory.__qualname__ = js_cls
                return factory

            setattr(ns, js_class, make_factory(js_class, cls, defn))

        return ns

    async def make_timer(self, duration=0):
        """Create a Timer (non-visual) and return its widget wrapper."""
        ns = self.get_widgets()
        return await ns.Timer(duration=duration)

    async def close(self):
        """Close this session's WebSocket connection."""
        if self._ws is not None:
            await self._ws.close()

    def __repr__(self):
        return f"<Session id={self._id}>"


class Application:
    """
    Main entry point for an async pgwidgets application.

    Creates a WebSocket server for widget commands and optionally an HTTP
    server to serve the JS/CSS assets.  Each browser connection gets its
    own Session.

    Parameters
    ----------
    ws_port : int
        WebSocket server port (default 9500).
    http_port : int
        HTTP file server port (default 9501). Ignored if http_server=False.
    host : str
        Bind address (default '127.0.0.1').
    http_server : bool
        Whether to start the built-in HTTP server (default True).
        Set to False if you are serving the pgwidgets static files
        from your own HTTP/HTTPS server (e.g. FastAPI, aiohttp, nginx).
    concurrency_handling : str
        How widget callbacks are dispatched.  One of:

        ``"per_session"`` (default)
            Each session gets its own asyncio.Lock.  Callbacks within
            a session are serialized, but different sessions' callbacks
            can interleave at await points.
        ``"serialized"``
            All callbacks from all sessions are serialized under a
            single global asyncio.Lock.
        ``"concurrent"``
            Callbacks are dispatched freely via ensure_future with no
            serialization.
    max_sessions : int or None
        Maximum number of concurrent sessions (default 1).
        Set to None for unlimited.  When the limit is reached, new
        connections are held until an existing session disconnects.
    """

    def __init__(self, ws_port=9500, http_port=9501, host="127.0.0.1",
                 http_server=True, concurrency_handling="per_session",
                 max_sessions=1):
        if concurrency_handling not in _CONCURRENCY_MODES:
            raise ValueError(
                f"concurrency_handling must be one of "
                f"{_CONCURRENCY_MODES!r}, got {concurrency_handling!r}")
        self._host = host
        self._ws_port = ws_port
        self._http_port = http_port
        self._use_http_server = http_server
        self._concurrency = concurrency_handling
        self._max_sessions = max_sessions

        self._favicon_path = Path(get_static_path()) / "icons" / "pgicon.svg"

        self._sessions = {}          # session_id -> Session
        self._next_session_id = 1
        self._on_connect = None      # user callback: fn(session)
        self._on_disconnect = None   # user callback: fn(session)
        self._session_semaphore = None  # initialized in start()
        self._cb_lock = None         # for "serialized" mode

        self._run_future = None      # set in run(), cancelled by close()
        self._httpd = None           # HTTP server instance

        # build widget classes once, shared by all sessions
        self._widget_classes = build_all_widget_classes()

    def on_connect(self, handler):
        """Register a callback invoked when a new session is created.

        The handler receives one argument: the Session object.
        Handler can be sync or async.  Use it to build the UI::

            @app.on_connect
            async def setup(session):
                Widgets = session.get_widgets()
                top = await Widgets.TopLevel(title="Hello")
                await top.show()

        Can also be used as a decorator.
        """
        self._on_connect = handler
        return handler

    def on_disconnect(self, handler):
        """Register a callback invoked when a session disconnects.

        The handler receives one argument: the Session object.
        Handler can be sync or async.  Can also be used as a decorator.
        """
        self._on_disconnect = handler
        return handler

    @property
    def sessions(self):
        """Dict of active sessions (session_id -> Session)."""
        return dict(self._sessions)

    @property
    def url(self):
        if self._use_http_server:
            return f"http://{self._host}:{self._http_port}/"
        return None

    @property
    def static_path(self):
        """Path to the pgwidgets static files directory."""
        return get_static_path()

    @property
    def remote_html(self):
        """Path to the remote.html connector page."""
        return get_remote_html()

    def set_favicon(self, path):
        """Set a custom favicon for the built-in HTTP server.

        Call this before start() to override the default pgwidgets icon.

        Parameters
        ----------
        path : str or Path
            Path to an image file (SVG, PNG, ICO, etc.).
        """
        self._favicon_path = Path(path)

    # -- WebSocket handling --

    async def _ws_handler(self, ws):
        # If max_sessions is set, wait for a slot.
        if self._session_semaphore is not None:
            await self._session_semaphore.acquire()

        # Allocate session.
        session_id = self._next_session_id
        self._next_session_id += 1

        session = Session(self, ws, session_id)

        # Set up per-session lock if needed.
        if self._concurrency == "per_session":
            session._cb_lock = asyncio.Lock()

        # Init handshake: reset the browser to a clean slate.
        await ws.send(json.dumps({"type": "init", "id": 0}))
        await ws.recv()  # wait for ack

        self._sessions[session_id] = session
        print(f"Session {session_id} connected.")

        # Launch on_connect as a concurrent task so it runs alongside
        # the message loop below — on_connect sends widget commands
        # whose responses must be read by the message loop.
        if self._on_connect:
            result = self._on_connect(session)
            if hasattr(result, "__await__"):
                asyncio.ensure_future(result)

        try:
            async for message in ws:
                session._handle_message(message)
        finally:
            self._sessions.pop(session_id, None)

            print(f"Session {session_id} disconnected.")

            if self._on_disconnect:
                result = self._on_disconnect(session)
                if hasattr(result, "__await__"):
                    await result

            if self._session_semaphore is not None:
                self._session_semaphore.release()

    # -- HTTP server --

    async def _start_http_server(self):
        """Start a simple HTTP server to serve the JS/CSS assets."""
        static_path = str(get_static_path())
        remote_html = get_remote_html()
        favicon_path = self._favicon_path

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=static_path, **kw)

            def do_GET(self):
                if self.path == "/" or self.path == "/index.html":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(remote_html.read_bytes())
                    return
                if self.path == "/favicon.svg" or self.path == "/favicon.ico":
                    if favicon_path and favicon_path.is_file():
                        mime, _ = mimetypes.guess_type(str(favicon_path))
                        self.send_response(200)
                        self.send_header("Content-Type",
                                         mime or "image/svg+xml")
                        self.end_headers()
                        self.wfile.write(favicon_path.read_bytes())
                    else:
                        self.send_error(404)
                    return
                super().do_GET()

            def log_message(self, format, *args):
                pass

        loop = asyncio.get_event_loop()
        import http.server
        self._httpd = http.server.HTTPServer(
            (self._host, self._http_port), Handler)
        await loop.run_in_executor(None, self._httpd.serve_forever)

    # -- Main loop --

    async def start(self):
        """Start the WebSocket server (and HTTP server if enabled).

        Call this after construction and any customisation.  Subclasses
        can override to add extra setup before or after the servers start.
        """
        if self._max_sessions is not None:
            self._session_semaphore = asyncio.Semaphore(
                self._max_sessions)

        if self._concurrency == "serialized":
            self._cb_lock = asyncio.Lock()

        if self._use_http_server:
            print(f"Open {self.url} in a browser to connect.")
            asyncio.ensure_future(self._start_http_server())
        print(f"WebSocket on ws://{self._host}:{self._ws_port}")

        self._ws_server = await websockets.serve(
            self._ws_handler, self._host, self._ws_port)

    async def close(self):
        """Close all sessions and shut down the application.

        Causes run() to return so the program can exit cleanly.
        """
        # Close all active sessions.
        for session in list(self._sessions.values()):
            await session.close()

        # Stop the WebSocket server.
        if hasattr(self, '_ws_server'):
            self._ws_server.close()
            await self._ws_server.wait_closed()

        # Stop the HTTP server (runs in a thread).
        if self._httpd is not None:
            self._httpd.shutdown()

        # Cancel the run() future so run() returns.
        if self._run_future is not None and not self._run_future.done():
            self._run_future.cancel()

    async def run(self):
        """Start servers and run forever. Ctrl-C to exit."""
        await self.start()
        self._run_future = asyncio.get_event_loop().create_future()
        try:
            await self._run_future
        except asyncio.CancelledError:
            pass
        finally:
            await self.close()
            print("\nShutting down.")
