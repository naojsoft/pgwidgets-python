"""
Synchronous Application and Session classes.

Application — starts a WebSocket server and HTTP file server, manages
session lifecycle.

Session — one per browser connection, owns the widget tree and
callbacks for that connection.
"""

import asyncio
import json
import logging
import mimetypes
import queue
import threading
import traceback
import http.server
import functools
from pathlib import Path

import websockets

from pgwidgets_js import get_static_path, get_remote_html
from pgwidgets.defs import WIDGETS
from pgwidgets.sync.widget import Widget, build_all_widget_classes

_CONCURRENCY_MODES = ("serialized", "per_session", "concurrent")


class _Namespace:
    """Holds widget factory methods as attributes (W.Button, W.Label, etc.)."""
    pass


def _run_queue_loop(cb_queue, stop_event):
    """Drain a callback queue until stop_event is set.

    Used by per-session threads and the main-thread serialized loop.
    Each item is a 4-tuple (handler, args, kwargs, result_slot).
    """
    while not stop_event.is_set():
        try:
            handler, args, kwargs, result_slot = \
                cb_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        try:
            rv = handler(*args, **kwargs)
            if result_slot is not None:
                result_slot['value'] = rv
        except Exception as e:
            if result_slot is not None:
                result_slot['error'] = e
            else:
                traceback.print_exc()
        finally:
            if result_slot is not None:
                result_slot['event'].set()


class Session:
    """
    A single browser connection with its own widget tree.

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
        self._lock = threading.Lock()
        self._results = {}       # msg id -> result dict
        self._events = {}        # msg id -> threading.Event
        self._callbacks = {}     # "wid:action" -> handler fn
        self._widget_map = {}    # wid -> Widget instance

        self._widget_classes = app._widget_classes
        self._transfers = {}     # transfer_id -> transfer state dict

        # Per-session callback queue + thread (for "per_session" mode).
        self._cb_queue = None
        self._cb_thread = None
        self._stop_event = None

    @property
    def id(self):
        """Unique session identifier."""
        return self._id

    @property
    def app(self):
        """The Application this session belongs to."""
        return self._app

    def _start_session_thread(self):
        """Start a per-session callback thread."""
        self._cb_queue = queue.Queue()
        self._stop_event = threading.Event()
        self._cb_thread = threading.Thread(
            target=_run_queue_loop,
            args=(self._cb_queue, self._stop_event),
            daemon=True,
            name=f"session-{self._id}",
        )
        self._cb_thread.start()

    def _stop_session_thread(self):
        """Stop the per-session callback thread."""
        if self._stop_event is not None:
            self._stop_event.set()
        if self._cb_thread is not None:
            self._cb_thread.join(timeout=2)

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
            event = self._events.get(msg_id)
            if event:
                self._results[msg_id] = msg
                event.set()

        elif msg_type == "file-chunk":
            self._handle_file_chunk(msg)

        elif msg_type == "callback":
            # If the payload has a transfer_id, stash the metadata —
            # the end callback fires after all chunks arrive.
            if (msg.get("args")
                    and isinstance(msg["args"][0], dict)
                    and "transfer_id" in msg["args"][0]):
                payload = msg["args"][0]
                tid = payload["transfer_id"]
                action = msg["action"]
                self._transfers[tid] = {
                    "wid": msg["wid"],
                    "action": action,
                    "payload": payload,
                    "file_data": {},   # file_index -> [chunk, ...]
                    "num_chunks": {},  # file_index -> expected count
                }
                # Fire a start callback with metadata (no file data).
                if action == "drop-end":
                    self._dispatch_callback(
                        msg["wid"], "drop-start", payload)
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
        # Map original action to its progress callback name.
        action = transfer["action"]
        progress_action = ("drop-progress" if action == "drop-end"
                           else "progress")
        self._dispatch_callback(
            transfer["wid"], progress_action, progress_info)

        if all_complete:
            # Reassemble file data and fire the original callback.
            payload = transfer["payload"]
            for i, file_meta in enumerate(payload["files"]):
                file_meta["data"] = "".join(
                    transfer["file_data"].get(i, []))
            del self._transfers[tid]
            self._dispatch_callback(
                transfer["wid"], action, payload)

    def _dispatch_callback(self, wid, action, *args):
        """Dispatch a callback through the configured concurrency mode."""
        key = f"{wid}:{action}"
        handler = self._callbacks.get(key)
        if not handler:
            return
        cb_args = (wid, *args)
        mode = self._app._concurrency
        if mode == "serialized":
            self._app._cb_queue.put((handler, cb_args, {}, None))
        elif mode == "per_session":
            self._cb_queue.put((handler, cb_args, {}, None))
        else:  # concurrent
            threading.Thread(
                target=handler, args=cb_args, daemon=True
            ).start()

    def _send(self, msg):
        """Send a message and block until the result arrives."""
        with self._lock:
            msg_id = self._next_id
            self._next_id += 1
        msg["id"] = msg_id
        event = threading.Event()
        self._events[msg_id] = event
        asyncio.run_coroutine_threadsafe(
            self._ws.send(json.dumps(msg)), self._app._loop
        )
        event.wait()
        result = self._results.pop(msg_id)
        del self._events[msg_id]
        if result.get("type") == "error":
            raise RuntimeError(result["error"])
        return result

    def _alloc_wid(self):
        with self._lock:
            wid = self._next_wid
            self._next_wid += 1
        return wid

    # -- Low-level widget API --

    def _create(self, js_class, *args):
        """Create a JS widget and return its wid."""
        wid = self._alloc_wid()
        resolved = [self._resolve_arg(a) for a in args]
        self._send({
            "type": "create",
            "wid": wid,
            "class": js_class,
            "args": resolved,
        })
        return wid

    def _call(self, wid, method, *args):
        """Call a method on a JS widget."""
        result = self._send({
            "type": "call",
            "wid": wid,
            "method": method,
            "args": list(args),
        })
        return result.get("value")

    def _listen(self, wid, action, handler):
        """Register a callback listener."""
        key = f"{wid}:{action}"
        self._callbacks[key] = handler
        self._send({
            "type": "listen",
            "wid": wid,
            "action": action,
        })

    def _unlisten(self, wid, action):
        """Remove a callback listener."""
        key = f"{wid}:{action}"
        self._callbacks.pop(key, None)
        self._send({
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
        """Return a namespace with factory methods for all widget types.

        Usage:
            Widgets = session.get_widgets()
            btn = Widgets.Button("Click me")
            vbox = Widgets.VBox(spacing=8)
        """
        ns = _Namespace()
        session = self

        for js_class, cls in self._widget_classes.items():
            defn = WIDGETS[js_class]

            def make_factory(js_cls, widget_cls, widget_defn):
                def factory(*args, **kwargs):
                    # split positional args from options kwargs
                    pos_names = widget_defn.get("args", [])
                    opt_names = widget_defn.get("options", [])

                    # build the JS constructor args list
                    js_args = list(args[:len(pos_names)])

                    # remaining positional args go into options too
                    for i, val in enumerate(args[len(pos_names):]):
                        if i < len(opt_names):
                            kwargs[opt_names[i]] = val

                    # build options dict from kwargs that match option names
                    options = {}
                    for k in list(kwargs.keys()):
                        if k in opt_names:
                            options[k] = kwargs.pop(k)

                    if options:
                        js_args.append(options)

                    wid = session._create(js_cls, *js_args)
                    widget = widget_cls(session, wid, js_cls)
                    session._widget_map[wid] = widget

                    # apply remaining kwargs as method calls
                    # e.g. spacing=8 -> set_spacing(8)
                    for k, v in kwargs.items():
                        setter = f"set_{k}"
                        if hasattr(widget, setter):
                            getattr(widget, setter)(v)
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

    def gui_do(self, func, *args, **kwargs):
        """Schedule a function to run on this session's callback thread.
        Returns immediately without waiting for the result.

        In ``serialized`` mode this queues on the shared main thread.
        In ``per_session`` mode this queues on this session's thread.
        In ``concurrent`` mode this runs directly on the calling thread.
        """
        mode = self._app._concurrency
        if mode == "serialized":
            self._app._cb_queue.put((func, args, kwargs, None))
        elif mode == "per_session":
            self._cb_queue.put((func, args, kwargs, None))
        else:
            func(*args, **kwargs)

    def gui_call(self, func, *args, **kwargs):
        """Schedule a function to run on this session's callback thread
        and block until it completes. Returns the function's return value.

        In ``serialized`` mode this queues on the shared main thread.
        In ``per_session`` mode this queues on this session's thread.
        In ``concurrent`` mode this runs directly on the calling thread.
        """
        mode = self._app._concurrency
        if mode == "concurrent":
            return func(*args, **kwargs)
        q = self._app._cb_queue if mode == "serialized" \
            else self._cb_queue
        result_slot = {'value': None, 'error': None,
                       'event': threading.Event()}
        q.put((func, args, kwargs, result_slot))
        result_slot['event'].wait()
        if result_slot['error'] is not None:
            raise result_slot['error']
        return result_slot['value']

    def make_timer(self, duration=0):
        """Create a Timer (non-visual) and return its widget wrapper."""
        ns = self.get_widgets()
        return ns.Timer(duration=duration)

    def close(self):
        """Close this session's WebSocket connection.

        This triggers the normal disconnect cleanup: the on_disconnect
        callback fires, the session is removed from the Application,
        and the per-session thread (if any) is stopped.
        """
        if self._ws is not None:
            asyncio.run_coroutine_threadsafe(
                self._ws.close(), self._app._loop)

    def __repr__(self):
        return f"<Session id={self._id}>"


class Application:
    """
    Main entry point for a synchronous pgwidgets application.

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
        from your own HTTP/HTTPS server (e.g. Flask, FastAPI, nginx).
    concurrency_handling : str
        How widget callbacks are dispatched.  One of:

        ``"per_session"`` (default)
            Each session gets its own thread.  Callbacks within a
            session are dispatched sequentially on that thread, but
            different sessions run concurrently.  No locks needed
            within a session.
        ``"serialized"``
            All callbacks from all sessions are dispatched on the
            main thread inside run().  Simple single-threaded model,
            but one slow callback blocks every session.
        ``"concurrent"``
            Each callback fires on its own daemon thread.  Maximum
            concurrency, but the caller must manage thread safety
            for any shared state.
    max_sessions : int or None
        Maximum number of concurrent sessions (default 1).
        Set to None for unlimited.  When the limit is reached, new
        connections are held until an existing session disconnects.
    logger : logging.Logger or None
        Logger for status messages.  If None (default), a null logger
        is used and no output is produced.
    """

    def __init__(self, ws_port=9500, http_port=9501, host="127.0.0.1",
                 http_server=True, concurrency_handling="per_session",
                 max_sessions=1, logger=None):
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

        if logger is None:
            logger = logging.getLogger("pgwidgets")
            logger.addHandler(logging.NullHandler())
        self._logger = logger

        self._favicon_path = Path(get_static_path()) / "icons" / "pgicon.svg"

        self._sessions = {}          # session_id -> Session
        self._next_session_id = 1
        self._session_lock = threading.Lock()
        self._on_connect = None      # user callback: fn(session)
        self._on_disconnect = None   # user callback: fn(session)
        self._cb_queue = queue.Queue()  # for "serialized" mode

        self._loop = None
        self._thread = None
        self._session_semaphore = None  # initialized in start()

        # build widget classes once, shared by all sessions
        self._widget_classes = build_all_widget_classes()

    def on_connect(self, handler):
        """Register a callback invoked when a new session is created.

        The handler receives one argument: the Session object.  Use it
        to build the UI for that session::

            def on_connect(session):
                Widgets = session.get_widgets()
                top = Widgets.TopLevel(title="Hello")
                top.show()

            app.on_connect(on_connect)

        Can also be used as a decorator::

            @app.on_connect
            def setup(session):
                ...
        """
        self._on_connect = handler
        return handler

    def on_disconnect(self, handler):
        """Register a callback invoked when a session disconnects.

        The handler receives one argument: the Session object.
        Can also be used as a decorator.
        """
        self._on_disconnect = handler
        return handler

    def start(self):
        """Start the WebSocket server (and HTTP server if enabled).

        Call this after construction and any customisation.  Subclasses
        can override to add extra setup before or after the servers start.
        """
        self._loop = asyncio.new_event_loop()
        if self._max_sessions is not None:
            self._session_semaphore = asyncio.Semaphore(
                self._max_sessions)

        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        if self._use_http_server:
            self._start_http_server()
            self._logger.info(f"Open {self.url} in a browser to connect.")
        self._logger.info(f"WebSocket on ws://{self._host}:{self._ws_port}")

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve_ws())

    async def _serve_ws(self):
        async with websockets.serve(self._ws_handler, self._host,
                                    self._ws_port):
            await asyncio.Future()

    async def _ws_handler(self, ws):
        # If max_sessions is set, wait for a slot.
        if self._session_semaphore is not None:
            await self._session_semaphore.acquire()

        # Allocate session.
        with self._session_lock:
            session_id = self._next_session_id
            self._next_session_id += 1

        session = Session(self, ws, session_id)

        # Start per-session callback thread if needed.
        if self._concurrency == "per_session":
            session._start_session_thread()

        # Init handshake: reset the browser to a clean slate.
        await ws.send(json.dumps({"type": "init", "id": 0}))
        await ws.recv()  # wait for ack

        with self._session_lock:
            self._sessions[session_id] = session

        self._logger.info(f"Session {session_id} connected.")

        # Notify user code.
        if self._on_connect:
            self._dispatch(session, self._on_connect, (session,))

        try:
            async for message in ws:
                session._handle_message(message)
        finally:
            # Stop per-session thread.
            if self._concurrency == "per_session":
                session._stop_session_thread()

            with self._session_lock:
                self._sessions.pop(session_id, None)

            self._logger.info(f"Session {session_id} disconnected.")

            if self._on_disconnect:
                self._dispatch(session, self._on_disconnect, (session,))

            if self._session_semaphore is not None:
                self._session_semaphore.release()

    def _dispatch(self, session, handler, args):
        """Dispatch a callable according to the concurrency mode."""
        mode = self._concurrency
        if mode == "serialized":
            self._cb_queue.put((handler, args, {}, None))
        elif mode == "per_session":
            session._cb_queue.put((handler, args, {}, None))
        else:
            threading.Thread(
                target=handler, args=args, daemon=True
            ).start()

    def _start_http_server(self):
        static_path = str(get_static_path())
        remote_html = get_remote_html()
        favicon_path = self._favicon_path
        ws_host = self._host
        ws_port = self._ws_port

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=static_path, **kwargs)

            def do_GET(self):
                # serve remote.html at the root, with WS URL injected
                if self.path == "/" or self.path == "/index.html":
                    html = remote_html.read_text(encoding="utf-8")
                    inject = (
                        f'<script>window.PGWIDGETS_WS_URL'
                        f' = "ws://{ws_host}:{ws_port}";</script>\n')
                    html = html.replace("<head>",
                                        "<head>\n" + inject, 1)
                    body = html.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type",
                                     "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                # serve the favicon
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
                pass  # suppress HTTP logs

        self._httpd = http.server.HTTPServer(
            (self._host, self._http_port), Handler)
        self._http_thread = threading.Thread(
            target=self._httpd.serve_forever, daemon=True)
        self._http_thread.start()

    @property
    def sessions(self):
        """Dict of active sessions (session_id -> Session)."""
        with self._session_lock:
            return dict(self._sessions)

    @property
    def url(self):
        """URL to open in a browser to connect (built-in server only)."""
        if self._use_http_server:
            return f"http://{self._host}:{self._http_port}/"
        return None

    @property
    def static_path(self):
        """Path to the pgwidgets static files directory.
        Useful when serving files from your own HTTP server."""
        return get_static_path()

    @property
    def remote_html(self):
        """Path to the remote.html connector page.
        Useful when serving from your own HTTP server."""
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

    # -- Main loop --

    def close(self):
        """Close all sessions and stop the application.

        Closes every active session's WebSocket, stops the HTTP server
        (if running), and signals run() to return.
        """
        # Close all active sessions.
        with self._session_lock:
            sessions = list(self._sessions.values())
        for session in sessions:
            session.close()

        # Stop the HTTP server.
        if hasattr(self, '_httpd'):
            self._httpd.shutdown()

        # Signal run() to return.
        self._shutdown.set()

    def run(self):
        """Start servers and block forever processing callbacks. Ctrl-C to exit.

        Calls start() automatically if it hasn't been called yet.

        In ``serialized`` mode, callbacks are dispatched on this thread.
        In ``per_session`` and ``concurrent`` modes, callbacks run on
        other threads; this method simply sleeps.
        """
        if self._loop is None:
            self.start()
        self._shutdown = threading.Event()
        try:
            if self._concurrency == "serialized":
                _run_queue_loop(self._cb_queue, self._shutdown)
            else:
                self._run_idle_loop()
        except KeyboardInterrupt:
            pass
        finally:
            self._logger.info("Shutting down.")

    def _run_idle_loop(self):
        """Sleep until shutdown is signalled."""
        while not self._shutdown.is_set():
            self._shutdown.wait(timeout=1)
