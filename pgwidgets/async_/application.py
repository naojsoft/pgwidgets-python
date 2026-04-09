"""
Asynchronous Application class — starts a WebSocket server and HTTP file
server, manages the connection to the browser, and provides the widget
factory via get_widgets().
"""

import asyncio
import json
from http.server import SimpleHTTPRequestHandler
from functools import partial

import websockets

from pgwidgets_js import get_static_path, get_remote_html
from pgwidgets.defs import WIDGETS
from pgwidgets.async_.widget import Widget, build_all_widget_classes


class _Namespace:
    """Holds widget factory methods as attributes (W.Button, W.Label, etc.)."""
    pass


class Application:
    """
    Main entry point for an async pgwidgets application.

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
        from your own HTTP/HTTPS server (e.g. FastAPI, aiohttp, nginx).
    """

    def __init__(self, ws_port=9500, http_port=9501, host="127.0.0.1",
                 http_server=True):
        self._host = host
        self._ws_port = ws_port
        self._http_port = http_port
        self._use_http_server = http_server

        self._next_id = 1
        self._next_wid = 1
        self._pending = {}       # msg id -> Future
        self._callbacks = {}     # "wid:action" -> handler fn
        self._widget_map = {}    # wid -> Widget instance

        self._ws = None
        self._connected = asyncio.Event()

        self._widget_classes = build_all_widget_classes()

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

    async def wait_for_connection(self):
        """Wait until a browser connects."""
        await self._connected.wait()

    # -- WebSocket handling --

    async def _ws_handler(self, ws):
        self._ws = ws
        self._connected.set()
        try:
            async for message in ws:
                self._handle_message(message)
        finally:
            self._ws = None
            self._connected.clear()

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

        elif msg_type == "callback":
            key = f"{msg['wid']}:{msg['action']}"
            handler = self._callbacks.get(key)
            if handler:
                asyncio.ensure_future(
                    handler(msg["wid"], *msg.get("args", [])))

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

    # -- Low-level API --

    async def _create(self, js_class, *args):
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
        result = await self._send({
            "type": "call",
            "wid": wid,
            "method": method,
            "args": list(args),
        })
        return result.get("value")

    async def _listen(self, wid, action, handler):
        key = f"{wid}:{action}"
        self._callbacks[key] = handler
        await self._send({
            "type": "listen",
            "wid": wid,
            "action": action,
        })

    async def _unlisten(self, wid, action):
        key = f"{wid}:{action}"
        self._callbacks.pop(key, None)
        await self._send({
            "type": "unlisten",
            "wid": wid,
            "action": action,
        })

    def _resolve_arg(self, arg):
        if isinstance(arg, Widget):
            return {"__wid__": arg.wid}
        if isinstance(arg, list):
            return [self._resolve_arg(a) for a in arg]
        if isinstance(arg, dict):
            return {k: self._resolve_arg(v) for k, v in arg.items()}
        return arg

    def _resolve_return(self, val):
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
            W = app.get_widgets()
            btn = await W.Button("Click me")
        """
        ns = _Namespace()
        app = self

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

                    wid = await app._create(js_cls, *js_args)
                    widget = widget_cls(app, wid, js_cls)
                    app._widget_map[wid] = widget

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

    # -- HTTP server (using asyncio) --

    async def _start_http_server(self):
        """Start a simple HTTP server to serve the JS/CSS assets."""
        static_path = str(get_static_path())
        remote_html = get_remote_html()

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
                super().do_GET()

            def log_message(self, format, *args):
                pass

        loop = asyncio.get_event_loop()
        import http.server
        server = http.server.HTTPServer((self._host, self._http_port), Handler)
        await loop.run_in_executor(None, server.serve_forever)

    # -- Main loop --

    async def start(self):
        """Start the WebSocket server (and HTTP server if enabled).

        Call this after construction and any customisation.  Subclasses
        can override to add extra setup before or after the servers start.
        """
        if self._use_http_server:
            print(f"Open {self.url} in a browser to connect.")
            asyncio.ensure_future(self._start_http_server())
        print(f"WebSocket on ws://{self._host}:{self._ws_port}")

        self._ws_server = await websockets.serve(
            self._ws_handler, self._host, self._ws_port)

    async def run(self):
        """Start servers and run forever."""
        await self.start()
        await asyncio.Future()  # run forever
