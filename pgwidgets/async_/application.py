"""
Asynchronous Application and Session classes.

Application — starts a WebSocket server and HTTP file server, manages
session lifecycle.

Session — owns a widget tree and persists independently of browser
connections.  Sessions can be created without a browser
(``Application.create_session()``) and survive disconnections so that
the UI can be reconstructed when a browser reconnects.
"""

import asyncio
import json
import logging
import mimetypes
import signal
import secrets
import traceback
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

import websockets

from pgwidgets_js import get_static_path, get_remote_html
from pgwidgets.defs import WIDGETS
from pgwidgets.method_types import (
    SPECIAL_SETTERS, FIXED_SETTERS, CHILD_METHODS as CHILD_METHOD_NAMES,
    STATE_SYNC_CALLBACKS, STATE_SYNC_REQUIRES_OPTION,
    WIDGET_CALLBACK_SYNC, POST_CHILDREN_STATE_KEYS, ITEM_LIST_CONFIG,
    CHILD_CLOSE_CALLBACKS, REPLAY_METHODS, TREE_VIEW_WIDGETS,
)
from pgwidgets.async_.widget import Widget, build_all_widget_classes

_CONCURRENCY_MODES = ("serialized", "per_session", "concurrent")


class _Namespace:
    """Holds widget factory methods as attributes (W.Button, W.Label, etc.)."""
    pass


class Session:
    """
    A session that owns a widget tree and its associated state.

    Sessions persist independently of browser connections.  A session
    can exist with no browser connected (e.g. after a disconnect or
    when created via ``Application.create_session()``).  One or more
    browsers can connect to the same session.

    Parameters
    ----------
    app : Application
        The owning Application.
    session_id : str or int
        Unique session identifier.
    ws : websockets.WebSocketServerProtocol or None
        Initial WebSocket connection, if any.
    """

    _STATE_KEY_TO_SETTER = {v: k for k, v in SPECIAL_SETTERS.items()}
    # e.g. {"size": "resize"}

    # State keys handled by fixed-value methods (show/hide)
    _FIXED_STATE_KEYS = {}
    for _mname, (_key, _val) in FIXED_SETTERS.items():
        _FIXED_STATE_KEYS.setdefault(_key, {})[_val] = _mname
    # e.g. {"visible": {True: "show", False: "hide"}}

    # State keys set by child methods — skip during state replay
    _CHILD_STATE_KEYS = set()

    def __init__(self, app, session_id, ws=None, token=None):
        self._app = app
        self._id = session_id
        self._token = token if token is not None else secrets.token_urlsafe(32)

        # Active browser connections for this session
        self._connections = [ws] if ws is not None else []

        self._next_id = 1
        self._next_wid = 1
        self._pending = {}       # msg id -> Future
        self._callbacks = {}     # "wid:action" -> handler fn
        self._widget_map = {}    # wid -> Widget instance
        self._root_widgets = []  # widgets with no parent (creation order)

        self._widget_classes = app._widget_classes
        self._transfers = {}     # transfer_id -> transfer state dict
        self._callback_source_ws = None  # ws that sent current callback

        self._reconstructing = False  # suppress callbacks during reconstruction

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

    @property
    def token(self):
        """Security token for reconnection."""
        return self._token

    @property
    def is_connected(self):
        """True if at least one browser is connected."""
        return len(self._connections) > 0

    @property
    def connections(self):
        """List of active WebSocket connections."""
        return list(self._connections)

    def add_connection(self, ws):
        """Add a browser connection to this session."""
        if ws not in self._connections:
            self._connections.append(ws)

    def remove_connection(self, ws):
        """Remove a browser connection from this session."""
        if ws in self._connections:
            self._connections.remove(ws)

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
        if self._reconstructing:
            return  # suppress callbacks during reconstruction

        # Auto-sync: some callbacks carry state that should be reflected
        # in the Python-side widget (e.g. move -> position, resize -> size).
        state_key = STATE_SYNC_CALLBACKS.get(action)
        if state_key is not None:
            widget = self._widget_map.get(wid)
            if widget is not None:
                if len(args) == 1 and isinstance(args[0], dict):
                    d = args[0]
                    if "width" in d and "height" in d:
                        new_val = (d["width"], d["height"])
                        if widget._state.get(state_key) != new_val:
                            widget._state[state_key] = new_val
                            self._push(wid, "resize",
                                       d["width"], d["height"])
                else:
                    new_val = tuple(args)
                    if widget._state.get(state_key) != new_val:
                        widget._state[state_key] = new_val
                        setter = (self._STATE_KEY_TO_SETTER.get(state_key)
                                  or f"set_{state_key}")
                        self._push(wid, setter, *args)
                # If this widget wraps a child (e.g. MDISubWindow),
                # propagate geometry into the parent's children options
                # so reconstruction replays with the current pos/size.
                content = getattr(widget, '_child_content', None)
                if content is not None and content._parent is not None:
                    for ch, ex_args, _ in content._parent._children:
                        if ch is content and ex_args:
                            opts = ex_args[0]
                            if isinstance(opts, dict):
                                val = widget._state[state_key]
                                if state_key == "position":
                                    opts["x"] = val[0]
                                    opts["y"] = val[1]
                                elif state_key == "size":
                                    opts["width"] = val[0]
                                    opts["height"] = val[1]
                            break

        # Per-widget-class sync: e.g. Slider.activated -> value
        widget = self._widget_map.get(wid)
        if widget is not None:
            cls_sync = WIDGET_CALLBACK_SYNC.get(widget._js_class)
            if cls_sync:
                spec = cls_sync.get(action)
                if spec is not None and args:
                    if isinstance(spec, list):
                        for idx, skey in spec:
                            if idx < len(args):
                                widget._state[skey] = args[idx]
                    else:
                        widget._state[spec] = args[0]

        # Tree/table expand/collapse/sort sync from browser interaction
        if widget is not None and action in ("expanded", "collapsed", "sorted"):
            if action == "expanded" and len(args) >= 2:
                path = args[1]
                key_path = tuple(path) if isinstance(path, list) else path
                expanded = widget._state.setdefault(
                    "_expanded_paths", set())
                expanded.add(key_path)
                collapsed = widget._state.get("_collapsed_paths")
                if collapsed is not None and collapsed != "_all":
                    collapsed.discard(key_path)
                self._push(wid, "expand_item", path)
            elif action == "collapsed" and len(args) >= 2:
                path = args[1]
                key_path = tuple(path) if isinstance(path, list) else path
                expanded = widget._state.get("_expanded_paths")
                if expanded is not None:
                    expanded.discard(key_path)
                collapsed = widget._state.setdefault(
                    "_collapsed_paths", set())
                if collapsed != "_all":
                    collapsed.add(key_path)
                self._push(wid, "collapse_item", path)
            elif action == "sorted" and len(args) >= 2:
                widget._state["_sort"] = (args[0], args[1])
                self._push(wid, "sort_by_column", args[0], args[1])

        # Cross-browser sync: push state changes to other browsers
        if widget is not None and len(self._connections) > 1:
            cls_sync = WIDGET_CALLBACK_SYNC.get(widget._js_class)
            if cls_sync:
                spec = cls_sync.get(action)
                if spec is not None and args:
                    if isinstance(spec, list):
                        for idx, skey in spec:
                            if idx < len(args):
                                setter = (self._STATE_KEY_TO_SETTER.get(skey)
                                          or f"set_{skey}")
                                self._push(wid, setter, args[idx])
                    else:
                        setter = (self._STATE_KEY_TO_SETTER.get(spec)
                                  or f"set_{spec}")
                        self._push(wid, setter, args[0])

        # Child-close callbacks (e.g. MDI page-close): remove the
        # closed child from the parent's _children so it won't be
        # reconstructed.
        if action in CHILD_CLOSE_CALLBACKS and args:
            parent = self._widget_map.get(wid)
            child = self._resolve_return(args[0])
            if parent is not None and isinstance(child, Widget):
                parent._children = [
                    entry for entry in parent._children
                    if entry[0] is not child
                ]
                child._parent = None
                self._push(wid, "close_child",
                           {"__wid__": child._wid})

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
        """Send a message to the primary browser and wait for the result.
        Secondary browsers receive a fire-and-forget copy.
        Returns None if no browsers are connected."""
        if not self._connections:
            return None
        msg_id = self._next_id
        self._next_id += 1
        msg["id"] = msg_id
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending[msg_id] = future
        payload = json.dumps(msg)
        # Primary: wait for result
        await self._connections[0].send(payload)
        # Secondary: fire-and-forget with separate id
        if len(self._connections) > 1:
            ff_id = self._next_id
            self._next_id += 1
            msg_copy = dict(msg, id=ff_id)
            ff_payload = json.dumps(msg_copy)
            for ws in self._connections[1:]:
                asyncio.ensure_future(ws.send(ff_payload))
        return await future


    def _push(self, wid, method, *args):
        """Push a silent call to all browsers except the callback source.
        Fire-and-forget: no result is awaited."""
        source = self._callback_source_ws
        targets = [ws for ws in self._connections if ws is not source]
        if not targets:
            return
        msg_id = self._next_id
        self._next_id += 1
        payload = json.dumps({
            "type": "call",
            "id": msg_id,
            "wid": wid,
            "method": method,
            "args": list(args),
            "silent": True,
        })
        for ws in targets:
            asyncio.ensure_future(ws.send(payload))

    def _fire_and_forget_listen(self, wid, action):
        """Send a listen message without awaiting a result.

        Used by _resolve_return (which is sync) to register auto-sync
        listeners.  The callback is already stored locally; this just
        tells the browser to start sending events.
        """
        if not self._connections:
            return
        msg_id = self._next_id
        self._next_id += 1
        payload = json.dumps({
            "type": "listen",
            "id": msg_id,
            "wid": wid,
            "action": action,
        })
        for ws in self._connections:
            asyncio.ensure_future(ws.send(payload))

    def _alloc_wid(self):
        wid = self._next_wid
        self._next_wid += 1
        return wid

    # -- Low-level widget API --

    async def _create(self, js_class, *args):
        """Create a JS widget and return its wid.

        If no browser is connected the widget is still allocated locally
        and will be created on the browser side during reconstruction.
        """
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
        """Call a method on a JS widget.

        Returns None if no browser is connected.
        """
        result = await self._send({
            "type": "call",
            "wid": wid,
            "method": method,
            "args": list(args),
        })
        if result is None:
            return None
        return result.get("value")

    async def _listen(self, wid, action, handler):
        """Register a callback listener.

        The handler is always stored locally.  If a browser is connected
        the listen message is sent immediately; otherwise it will be
        sent during reconstruction.
        """
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

    def _resolve_return(self, val, js_class=None):
        """Convert wire refs back to Widget instances in return values.

        If the wid isn't already tracked (e.g. JS-created MenuAction,
        ToolBarAction, MDISubWindow), a new Widget wrapper is created
        on the fly so Python code can call methods on it.
        """
        if isinstance(val, dict) and "__wid__" in val:
            wid = val["__wid__"]
            widget = self._widget_map.get(wid)
            if widget is not None:
                return widget
            # Auto-wrap JS-created widgets
            cls_name = js_class or val.get("__class__")
            cls = self._widget_classes.get(cls_name, Widget) if cls_name else Widget
            widget = cls._from_existing(self, wid, cls_name or "Widget")
            self._widget_map[wid] = widget
            # Auto-listen for state-syncing callbacks (move, resize)
            # so position/size changes are tracked for reconstruction.
            # Register locally (sync) and send the listen message as
            # true fire-and-forget (no result awaited) since
            # _resolve_return is not async.
            for action in STATE_SYNC_CALLBACKS:
                key = f"{wid}:{action}"
                self._callbacks[key] = lambda wid, *a: None
                widget._auto_sync_actions.add(action)
                self._fire_and_forget_listen(wid, action)
            return widget
        if isinstance(val, list):
            return [self._resolve_return(v) for v in val]
        return val

    # -- Widget factory --

    def get_widgets(self):
        """Return a namespace with widget classes bound to this session.

        Usage:
            W = session.get_widgets()
            btn = await W.Button("Click me")

        Each attribute is a thin wrapper that passes this session as
        the first argument to the widget class constructor.  The
        returned object is awaitable (two-phase async init).
        """
        ns = _Namespace()
        session = self

        for js_class, cls in self._widget_classes.items():
            def make_factory(widget_cls):
                def factory(*args, **kwargs):
                    return widget_cls(session, *args, **kwargs)
                factory.__name__ = widget_cls.__name__
                factory.__qualname__ = widget_cls.__qualname__
                return factory

            setattr(ns, js_class, make_factory(cls))

        return ns

    async def make_timer(self, duration=0):
        """Create a Timer (non-visual) and return its widget wrapper."""
        ns = self.get_widgets()
        return await ns.Timer(duration=duration)

    # -- Widget tree walking --

    def walk_widget_tree(self):
        """Yield all widgets in creation/tree order (parents before children).

        Starts from root widgets (those with no parent) and recurses
        depth-first through children.
        """
        def _walk(widget):
            yield widget
            for child, _args, _meth in widget._children:
                yield from _walk(child)

        for root in self._root_widgets:
            yield from _walk(root)

    # -- Reconstruction --

    async def _reconstruct_widget(self, widget):
        """Replay a single widget's creation, state, and callbacks."""
        defn = WIDGETS[widget._js_class]

        # 1. Create the widget with its original constructor args
        js_args = list(widget._constructor_args)
        if widget._constructor_options:
            js_args.append(dict(widget._constructor_options))
        resolved = [self._resolve_arg(a) for a in js_args]
        await self._send({
            "type": "create",
            "wid": widget._wid,
            "class": widget._js_class,
            "args": resolved,
        })

        # Compute which state keys were already set by the constructor
        constructor_keys = set()
        pos_names = defn.get("args", [])
        for i, name in enumerate(pos_names):
            if i < len(widget._constructor_args):
                constructor_keys.add(name)
        for k in widget._constructor_options:
            constructor_keys.add(k)

        # 2a. Replay item lists (e.g. ComboBox items)
        item_cfg = ITEM_LIST_CONFIG.get(widget._js_class)
        if item_cfg:
            items = widget._state.get(item_cfg["key"], [])
            append_method = item_cfg["append"]
            for item in items:
                await self._call(widget._wid, append_method, item)

        # 2b. Replay state that changed after construction
        for key, value in widget._state.items():
            if key in constructor_keys:
                if key in widget._constructor_options:
                    if value == widget._constructor_options[key]:
                        continue
                else:
                    idx = pos_names.index(key) if key in pos_names else -1
                    if (idx >= 0 and idx < len(widget._constructor_args)
                            and value == widget._constructor_args[idx]):
                        continue

            if key in self._CHILD_STATE_KEYS:
                continue
            if key in self._FIXED_STATE_KEYS:
                continue
            if key in POST_CHILDREN_STATE_KEYS:
                continue
            if key.startswith("_"):
                continue

            if key in self._STATE_KEY_TO_SETTER:
                method_name = self._STATE_KEY_TO_SETTER[key]
            else:
                method_name = f"set_{key}"

            if isinstance(value, tuple):
                await self._call(widget._wid, method_name, *value)
            else:
                await self._call(widget._wid, method_name, value)

        # 3. Attach to parent
        if widget._parent is not None:
            for child, extra_args, child_method in widget._parent._children:
                if child is widget:
                    resolved_widget = self._resolve_arg(widget)
                    resolved_args = [self._resolve_arg(a) for a in extra_args]
                    result = await self._call(
                        widget._parent._wid, child_method,
                        resolved_widget, *resolved_args)
                    result = self._resolve_return(result)
                    if (isinstance(result, Widget) and result is not widget):
                        result._child_content = widget
                    break

        # 4. Replay factory calls (e.g. add_action, add_name, add_separator)
        for i, (meth, call_args, old_widget) in enumerate(
                widget._replay_calls):
            resolved = [self._resolve_arg(a) for a in call_args]
            result = await self._call(widget._wid, meth, *resolved)
            new_widget = self._resolve_return(result)

            if (isinstance(old_widget, Widget)
                    and isinstance(new_widget, Widget)):
                for act, (handler, ea, ek, style) in \
                        old_widget._registered_callbacks.items():
                    if style == "on":
                        await new_widget.on(act, handler, *ea, **ek)
                    else:
                        await new_widget.add_callback(act, handler, *ea, **ek)
                # Replay callback-synced state
                cls_sync = WIDGET_CALLBACK_SYNC.get(
                    old_widget._js_class, {})
                sync_keys = set()
                for spec in cls_sync.values():
                    if isinstance(spec, list):
                        sync_keys.update(k for _, k in spec)
                    else:
                        sync_keys.add(spec)
                for key in sync_keys:
                    if key in old_widget._state:
                        value = old_widget._state[key]
                        setter = f"set_{key}"
                        if isinstance(value, tuple):
                            await self._call(new_widget._wid, setter, *value)
                        else:
                            await self._call(new_widget._wid, setter, value)
                        new_widget._state[key] = value
                # Re-register auto-sync listeners on the new widget
                for act in cls_sync:
                    if act not in new_widget._auto_sync_actions:
                        await self._listen(new_widget._wid, act,
                                           lambda wid, *a: None)
                        new_widget._auto_sync_actions.add(act)
                # Update the replay entry
                widget._replay_calls[i] = (meth, call_args, new_widget)

        # 5. Re-register callbacks
        for action, (handler, extra_args, extra_kwargs, style) in \
                widget._registered_callbacks.items():
            if style == "on":
                await widget.on(action, handler, *extra_args, **extra_kwargs)
            else:
                await widget.add_callback(action, handler, *extra_args,
                                          **extra_kwargs)

        # 6. Re-register auto-sync listeners
        for action in widget._auto_sync_actions:
            if action not in widget._registered_callbacks:
                await self._listen(widget._wid, action, lambda wid, *a: None)

    async def reconstruct(self):
        """Replay the entire widget tree to all connected browsers.

        Walks the widget tree in creation order and for each widget:
        1. Sends a create message with constructor args
        2. Replays state changes (setters)
        3. Attaches children to parents
        4. Re-registers callbacks

        Sends ``reconstruct-start`` / ``reconstruct-end`` bracket
        messages so the browser can suppress its own callback dispatch
        during reconstruction.

        This is called when a browser reconnects to an existing session.
        """
        # Clean up auto-wrapped widgets from the previous browser session.
        tree_wids = {w._wid for w in self.walk_widget_tree()}
        stale = [wid for wid in self._widget_map if wid not in tree_wids]
        for wid in stale:
            self._widget_map.pop(wid, None)
            stale_keys = [k for k in self._callbacks if k.startswith(f"{wid}:")]
            for k in stale_keys:
                del self._callbacks[k]

        await self._send({"type": "reconstruct-start",
                          "next_wid": self._next_wid})
        for widget in self.walk_widget_tree():
            await self._reconstruct_widget(widget)

        # Deferred state: replay after the full tree is assembled.
        for widget in self.walk_widget_tree():
            # Post-children state (e.g. Splitter sizes)
            for key, value in widget._state.items():
                if key not in POST_CHILDREN_STATE_KEYS:
                    continue

                # Tree/table expanded paths
                if key == "_expanded_paths":
                    if value == "_all":
                        await self._call(widget._wid, "expand_all")
                    elif isinstance(value, set):
                        for path in value:
                            await self._call(widget._wid, "expand_item",
                                             list(path))
                    continue

                # Tree/table collapsed paths
                if key == "_collapsed_paths":
                    if value == "_all":
                        await self._call(widget._wid, "collapse_all")
                    elif isinstance(value, set):
                        for path in value:
                            await self._call(widget._wid, "collapse_item",
                                             list(path))
                    continue

                # Tree/table sort
                if key == "_sort":
                    col, asc = value
                    await self._call(widget._wid, "sort_by_column", col, asc)
                    continue

                if key in self._STATE_KEY_TO_SETTER:
                    method_name = self._STATE_KEY_TO_SETTER[key]
                else:
                    method_name = f"set_{key}"
                if isinstance(value, tuple):
                    await self._call(widget._wid, method_name, *value)
                else:
                    await self._call(widget._wid, method_name, value)

            # Show/hide
            for key, value in widget._state.items():
                if key in self._FIXED_STATE_KEYS:
                    method_name = self._FIXED_STATE_KEYS[key].get(value)
                    if method_name:
                        await self._call(widget._wid, method_name)

        await self._send({"type": "reconstruct-end"})

    async def close(self):
        """Close all WebSocket connections for this session."""
        for ws in list(self._connections):
            await ws.close()

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
        # Init handshake: send init, receive ack which may contain
        # session_id + token for reconnection.
        await ws.send(json.dumps({"type": "init", "id": 0}))
        ack_data = await ws.recv()
        ack = json.loads(ack_data)
        reconnect_sid = ack.get("session_id")
        reconnect_token = ack.get("token")

        # Try to reconnect to an existing session.
        session = None
        is_reconnect = False
        if reconnect_sid is not None and reconnect_token is not None:
            existing = self._sessions.get(reconnect_sid)
            if existing is not None and existing.token == reconnect_token:
                session = existing
                is_reconnect = True
                self._logger.info(
                    f"Session {reconnect_sid}: browser reconnecting.")
            else:
                # Credentials were provided but invalid — reject.
                self._logger.warning(
                    f"Rejected connection: invalid session credentials "
                    f"(session_id={reconnect_sid}).")
                await ws.close(4001, "Invalid session credentials")
                return

        if session is None:
            # New session — acquire a slot if max_sessions is set.
            if self._session_semaphore is not None:
                await self._session_semaphore.acquire()

            session_id = self._next_session_id
            self._next_session_id += 1

            session = Session(self, session_id, ws=ws)

            # Set up per-session lock if needed.
            if self._concurrency == "per_session":
                session._cb_lock = asyncio.Lock()

            self._sessions[session_id] = session
        else:
            # Reconnecting — add this connection to the existing session.
            session.add_connection(ws)

        # Send session credentials so the browser can store them.
        await ws.send(json.dumps({
            "type": "session-info",
            "session_id": session.id,
            "token": session.token,
        }))

        if is_reconnect:
            async def do_reconstruct():
                self._logger.info(
                    f"Session {session.id}: reconstructing UI.")
                session._reconstructing = True
                try:
                    await session.reconstruct()
                finally:
                    session._reconstructing = False
                self._logger.info(
                    f"Session {session.id}: reconstruction complete.")
            asyncio.ensure_future(do_reconstruct())
        else:
            self._logger.info(f"Session {session.id} connected.")
            if self._on_connect:
                result = self._on_connect(session)
                if hasattr(result, "__await__"):
                    asyncio.ensure_future(result)

        try:
            async for message in ws:
                session._callback_source_ws = ws
                session._handle_message(message)
                session._callback_source_ws = None
        finally:
            session.remove_connection(ws)

            self._logger.info(
                f"Session {session.id}: browser disconnected "
                f"({len(session._connections)} remaining).")

            if self._on_disconnect:
                result = self._on_disconnect(session)
                if hasattr(result, "__await__"):
                    await result

            # Session stays in self._sessions for potential reconnection.
            if not is_reconnect and self._session_semaphore is not None:
                self._session_semaphore.release()

    def create_session(self, session_id=None, token=None):
        """Create a session without a browser connection.

        The session is registered immediately and can have its widget
        tree built up before any browser connects.  When a browser
        connects and presents the matching session ID and token, the
        existing session's UI will be reconstructed in that browser.

        Parameters
        ----------
        session_id : str or int or None
            An explicit session ID.  If None, one is auto-allocated.
        token : str or None
            An explicit security token for reconnection.  If None, one
            is auto-generated.

        Returns
        -------
        Session
            The newly created session.
        """
        if session_id is None:
            session_id = self._next_session_id
            self._next_session_id += 1
        elif session_id in self._sessions:
            raise ValueError(
                f"Session {session_id!r} already exists")

        session = Session(self, session_id, token=token)

        if self._concurrency == "per_session":
            session._cb_lock = asyncio.Lock()

        self._sessions[session_id] = session

        self._logger.info(
            f"Session {session_id} created (no browser).")
        return session

    # -- HTTP server --

    async def _start_http_server(self):
        """Start a simple HTTP server to serve the JS/CSS assets."""
        static_path = str(get_static_path())
        remote_html = get_remote_html()
        favicon_path = self._favicon_path
        ws_host = self._host
        ws_port = self._ws_port

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=static_path, **kw)

            def do_GET(self):
                # Strip query string for path matching (e.g. /?session=1)
                path = self.path.split("?")[0]
                if path == "/" or path == "/index.html":
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
            self._logger.info(f"Open {self.url} in a browser to connect.")
            asyncio.ensure_future(self._start_http_server())
        self._logger.info(
            f"WebSocket on ws://{self._host}:{self._ws_port}")

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
        """Start servers and run forever. Ctrl-C to exit cleanly."""
        await self.start()
        loop = asyncio.get_event_loop()
        self._run_future = loop.create_future()

        # Install SIGINT handler so Ctrl-C triggers a clean shutdown
        # instead of raising KeyboardInterrupt.
        loop.add_signal_handler(signal.SIGINT,
                                lambda: asyncio.ensure_future(self.close()))

        try:
            await self._run_future
        except asyncio.CancelledError:
            pass
        finally:
            loop.remove_signal_handler(signal.SIGINT)
            await self.close()
            self._logger.info("Shutting down.")
