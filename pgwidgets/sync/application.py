"""
Synchronous Application class — starts a WebSocket server and HTTP file
server, manages the connection to the browser, and provides the widget
factory via get_widgets().
"""

import asyncio
import json
import mimetypes
import queue
import threading
import http.server
import functools
from pathlib import Path

import websockets

from pgwidgets_js import get_static_path, get_remote_html
from pgwidgets.defs import WIDGETS
from pgwidgets.sync.widget import Widget, build_all_widget_classes


class _Namespace:
    """Holds widget factory methods as attributes (W.Button, W.Label, etc.)."""
    pass


class Application:
    """
    Main entry point for a synchronous pgwidgets application.

    Creates a WebSocket server for widget commands and optionally an HTTP
    server to serve the JS/CSS assets.  Call run() to block on the event loop.

    Parameters
    ----------
    ws_port : int
        WebSocket server port (default 9500).
    http_port : int
        HTTP file server port (default 9501). Ignored if http_server=False.
    host : str
        Bind address (default 'localhost').
    http_server : bool
        Whether to start the built-in HTTP server (default True).
        Set to False if you are serving the pgwidgets static files
        from your own HTTP/HTTPS server (e.g. Flask, FastAPI, nginx).
    thread_safe : bool
        Callback threading model (default True).
        If True, all widget callbacks are queued and dispatched
        sequentially on the main thread inside run(). This is the
        standard GUI-toolkit model (like Qt/GTK) — callbacks see a
        consistent world and don't need locks.
        If False, each callback fires on its own daemon thread,
        allowing concurrent execution but requiring the caller to
        manage thread safety for any shared state.
    """

    def __init__(self, ws_port=9500, http_port=9501, host="127.0.0.1",
                 http_server=True, thread_safe=True):
        self._host = host
        self._ws_port = ws_port
        self._http_port = http_port
        self._use_http_server = http_server
        self._thread_safe = thread_safe

        self._favicon_path = Path(get_static_path()) / "icons" / "pgicon.svg"

        self._next_id = 1
        self._next_wid = 1
        self._lock = threading.Lock()
        self._results = {}       # msg id -> result dict
        self._events = {}        # msg id -> threading.Event
        self._callbacks = {}     # "wid:action" -> handler fn
        self._widget_map = {}    # wid -> Widget instance
        self._cb_queue = queue.Queue()  # for thread_safe mode

        self._ws = None
        self._loop = None
        self._connected = threading.Event()

        self._loop = None
        self._thread = None
        self._initialized = False

        # build widget classes
        self._widget_classes = build_all_widget_classes()

    def start(self):
        """Start the WebSocket server (and HTTP server if enabled).

        Call this after construction and any customisation.  Subclasses
        can override to add extra setup before or after the servers start.
        """
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        if self._use_http_server:
            self._start_http_server()
            print(f"Open {self.url} in a browser to connect.")
        print(f"WebSocket on ws://{self._host}:{self._ws_port}")

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._serve_ws())

    async def _serve_ws(self):
        async with websockets.serve(self._ws_handler, self._host,
                                    self._ws_port):
            await asyncio.Future()

    async def _ws_handler(self, ws):
        self._ws = ws
        if not self._initialized:
            # First connection: reset the browser to a clean slate.
            await ws.send(json.dumps({"type": "init", "id": 0}))
            await ws.recv()  # wait for ack
            self._next_wid = 1
            self._widget_map.clear()
            self._callbacks.clear()
            self._initialized = True
        self._connected.set()
        try:
            async for message in ws:
                self._handle_message(message)
        finally:
            self._ws = None
            self._connected.clear()

    def _start_http_server(self):
        static_path = str(get_static_path())
        remote_html = get_remote_html()
        favicon_path = self._favicon_path

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=static_path, **kwargs)

            def do_GET(self):
                # serve remote.html at the root
                if self.path == "/" or self.path == "/index.html":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.end_headers()
                    self.wfile.write(remote_html.read_bytes())
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

    def wait_for_connection(self):
        """Block until a browser connects."""
        self._connected.wait()

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

        elif msg_type == "callback":
            key = f"{msg['wid']}:{msg['action']}"
            handler = self._callbacks.get(key)
            if handler:
                cb_args = (msg["wid"], *msg.get("args", []))
                if self._thread_safe:
                    self._cb_queue.put((handler, cb_args, {}, None))
                else:
                    threading.Thread(
                        target=handler,
                        args=cb_args,
                        daemon=True
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
            self._ws.send(json.dumps(msg)), self._loop
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

    # -- Public low-level API --

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
            W = app.get_widgets()
            btn = W.Button("Click me")
            vbox = W.VBox(spacing=8)
        """
        ns = _Namespace()
        app = self

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

                    wid = app._create(js_cls, *js_args)
                    widget = widget_cls(app, wid, js_cls)
                    app._widget_map[wid] = widget

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
        """Schedule a function to run on the GUI thread. Returns
        immediately without waiting for the result.

        In thread_safe mode this queues the call. In multi-thread mode
        this runs the function directly on the calling thread.
        """
        if self._thread_safe:
            self._cb_queue.put((func, args, kwargs, None))
        else:
            func(*args, **kwargs)

    def gui_call(self, func, *args, **kwargs):
        """Schedule a function to run on the GUI thread and block until
        it completes. Returns the function's return value.

        In thread_safe mode this queues the call and waits. In
        multi-thread mode this runs the function directly on the
        calling thread and returns its result.
        """
        if self._thread_safe:
            result_slot = {'value': None, 'error': None,
                           'event': threading.Event()}
            self._cb_queue.put((func, args, kwargs, result_slot))
            result_slot['event'].wait()
            if result_slot['error'] is not None:
                raise result_slot['error']
            return result_slot['value']
        else:
            return func(*args, **kwargs)

    def make_timer(self, duration=0):
        """Create a Timer (non-visual) and return its widget wrapper."""
        ns = self.get_widgets()
        return ns.Timer(duration=duration)

    # -- Main loop --

    def run(self):
        """Block forever, processing callbacks. Ctrl-C to exit.

        In thread_safe mode (the default), callbacks are dispatched
        sequentially on this thread.  In multi-thread mode, this method
        simply sleeps while callbacks run on their own threads.
        """
        try:
            if self._thread_safe:
                self._run_gui_loop()
            else:
                self._run_idle_loop()
        except KeyboardInterrupt:
            print("\nShutting down.")

    def _run_gui_loop(self):
        """Process the callback queue on the main thread."""
        while True:
            try:
                handler, args, kwargs, result_slot = \
                    self._cb_queue.get(timeout=0.5)
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
                    import traceback
                    traceback.print_exc()
            finally:
                if result_slot is not None:
                    result_slot['event'].set()

    def _run_idle_loop(self):
        """Sleep forever — callbacks run on their own threads."""
        import time
        while True:
            time.sleep(1)
