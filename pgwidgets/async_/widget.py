"""
Asynchronous stateful Widget class and widget class factory.

Widgets store their state locally (text, color, size, children, etc.)
so the Python side is the source of truth.  Getters return from local
state without a browser round-trip.  On reconnection, the widget tree
can be walked and the full UI reconstructed.
"""

import base64
import mimetypes
import os

from pgwidgets.defs import WIDGETS, CALLBACK_METHODS, WIDGET_METHODS, CONTAINER_METHODS
from pgwidgets.method_types import (
    classify_method, SETTER, GETTER, CHILD, ACTION, JS_ONLY,
    CHILD_METHODS as CHILD_METHOD_TYPES,
    FIXED_SETTERS, CLEAR_RESETS, ITEM_LIST_CONFIG,
    REPLAY_METHODS, CHILD_SELECT_METHODS, TREE_VIEW_WIDGETS,
    STATE_SYNC_CALLBACKS, STATE_SYNC_REQUIRES_OPTION,
    WIDGET_CALLBACK_SYNC, CHILD_CLOSE_CALLBACKS,
    FACTORY_RETURN_TYPES, UNSUPPORTED_METHODS,
)


class Widget:
    """Base class for all asynchronous widget wrappers.

    Subclasses are generated from widget definitions and have proper
    constructors with named parameters::

        btn = await Button(session, "Click me", icon="path/to/icon.png")

    The first argument is always the session.  Remaining arguments
    match the widget definition's ``args`` and ``options``.

    Because async operations cannot happen in ``__init__``, the
    constructor returns a coroutine via ``__await__`` that completes
    the JS-side creation.

    Stores local state so the Python side can serve as the source of
    truth for the UI.
    """

    # Set by build_widget_class() on generated subclasses.
    _js_class_name = None
    _defn = None

    def __init__(self, session, *args, **kwargs):
        """Create a widget and register it with the session.

        Parameters
        ----------
        session : Session
            The session this widget belongs to.
        *args
            Positional arguments matching the widget definition's ``args``
            and ``options`` lists.
        **kwargs
            Keyword arguments matching the widget definition's ``options``
            list.  Extra kwargs are applied as ``set_<name>()`` calls.
        """
        defn = self._defn
        if defn is None:
            raise TypeError(
                "Cannot instantiate Widget directly. "
                "Use a specific widget class (e.g. Button, Label).")

        js_class = self._js_class_name

        # Initialize state containers
        self._session = session
        self._js_class = js_class
        self._state = {}
        self._children = []
        self._parent = None
        self._constructor_args = ()
        self._constructor_options = {}
        self._registered_callbacks = {}
        self._auto_sync_actions = set()
        self._replay_calls = []

        # Parse args/kwargs against definition
        pos_names = defn.get("args", [])
        opt_names = defn.get("options", [])

        js_args = list(args[:len(pos_names)])

        for i, val in enumerate(args[len(pos_names):]):
            if i < len(opt_names):
                kwargs[opt_names[i]] = val

        options = {}
        for k in list(kwargs.keys()):
            if k in opt_names:
                options[k] = kwargs.pop(k)

        if options:
            # Keep positional slots so the options dict doesn't slide
            # into a positional arg position on the JS side
            js_args.append(options)
        else:
            # Strip trailing Nones when no options follow
            while js_args and js_args[-1] is None:
                js_args.pop()

        # Store parsed info for _initialize() and reconstruction
        self._init_js_args = js_args
        self._init_pos_names = pos_names
        self._init_args = args
        self._init_options = options
        self._init_extra_kwargs = kwargs

    async def _initialize(self):
        """Complete the async portion of widget creation.

        Called automatically by ``__await__``.
        """
        session = self._session
        js_class = self._js_class
        js_args = self._init_js_args
        pos_names = self._init_pos_names
        args = self._init_args
        options = self._init_options
        kwargs = self._init_extra_kwargs

        # Allocate wid and create on JS side
        wid = await session._create(js_class, *js_args)
        self._wid = wid
        session._widget_map[wid] = self

        # Store constructor info for reconstruction
        self._constructor_args = tuple(args[:len(pos_names)])
        self._constructor_options = dict(options)

        # Store constructor args as initial state
        for i, name in enumerate(pos_names):
            if i < len(args):
                self._state[name] = args[i]
        for k, v in options.items():
            self._state[k] = v

        # Apply remaining kwargs as setter calls
        for k, v in kwargs.items():
            setter = f"set_{k}"
            if hasattr(self, setter):
                await getattr(self, setter)(v)
            else:
                raise TypeError(
                    f"{js_class}() got unexpected keyword "
                    f"argument '{k}'")

        # Register auto-sync listeners
        await self._register_auto_sync()

        # Track as root widget (may be reparented later)
        session._root_widgets.append(self)

        # Clean up init temporaries
        del self._init_js_args
        del self._init_pos_names
        del self._init_args
        del self._init_options
        del self._init_extra_kwargs

        return self

    def __await__(self):
        return self._initialize().__await__()

    @classmethod
    def _from_existing(cls, session, wid, js_class):
        """Create a Widget wrapper for an already-existing JS widget.

        Used internally by ``_resolve_return`` and ``_reconstruct_widget``
        to wrap widgets that were created on the JS side or are being
        replayed during reconstruction.
        """
        obj = cls.__new__(cls)
        obj._session = session
        obj._wid = wid
        obj._js_class = js_class
        obj._state = {}
        obj._children = []
        obj._parent = None
        obj._constructor_args = ()
        obj._constructor_options = {}
        obj._registered_callbacks = {}
        obj._auto_sync_actions = set()
        obj._replay_calls = []
        return obj

    async def _register_auto_sync(self):
        """Register auto-sync listeners for state tracking and cross-browser sync."""
        defn = self._defn
        if defn is None:
            return
        session = self._session
        wid = self._wid
        js_class = self._js_class

        opt_names_set = set(defn.get("options", []))
        all_callbacks = defn.get("callbacks", [])

        # State-sync callbacks (move -> position, resize -> size)
        for action in STATE_SYNC_CALLBACKS:
            req_opt = STATE_SYNC_REQUIRES_OPTION.get(action)
            if req_opt and req_opt not in opt_names_set:
                continue
            if req_opt is None and action not in all_callbacks:
                continue
            await session._listen(wid, action, lambda wid, *a: None)
            self._auto_sync_actions.add(action)

        # Per-widget-class state sync (e.g. Slider "activated" -> value)
        cls_sync = WIDGET_CALLBACK_SYNC.get(js_class, {})
        for action in cls_sync:
            if action not in self._auto_sync_actions:
                await session._listen(wid, action, lambda wid, *a: None)
                self._auto_sync_actions.add(action)

        # Child-close callbacks (e.g. MDI page-close)
        for action in CHILD_CLOSE_CALLBACKS:
            if action in all_callbacks:
                await session._listen(wid, action, lambda wid, *a: None)
                self._auto_sync_actions.add(action)

        # Tree/table state callbacks
        if js_class in TREE_VIEW_WIDGETS:
            for action in ("expanded", "collapsed", "sorted"):
                if action not in self._auto_sync_actions:
                    await session._listen(wid, action, lambda wid, *a: None)
                    self._auto_sync_actions.add(action)

    @property
    def wid(self):
        return self._wid

    @property
    def session(self):
        """The Session this widget belongs to."""
        return self._session

    @property
    def app(self):
        """The Application this widget belongs to."""
        return self._session.app

    # Methods whose string arguments may be local file paths that need
    # to be converted to data URIs before sending to the browser.
    _FILE_ARG_METHODS = frozenset([
        "set_icon", "set_image", "set_icon_gutter",
    ])

    @staticmethod
    def _resolve_file_arg(val):
        """If val is a string that refers to an existing file, convert
        it to a data URI.  Otherwise return it unchanged."""
        if isinstance(val, str) and os.path.isfile(val):
            return Widget._to_data_uri(val)
        return val

    async def _call(self, method, *args):
        """Call a method on the JS widget."""
        if method in self._FILE_ARG_METHODS:
            args = tuple(self._resolve_file_arg(a) for a in args)
        resolved = [self._session._resolve_arg(a) for a in args]
        result = await self._session._call(self._wid, method, *resolved)
        return self._session._resolve_return(result)

    async def on(self, action, handler, *extra_args, **extra_kwargs):
        """Register a callback. The handler receives
        ``(*callback_args, *extra_args, **extra_kwargs)`` -- no widget arg.
        Handler can be sync or async.
        Multiple handlers can be registered for the same action."""
        # Store for reconstruction
        self._registered_callbacks.setdefault(action, []).append(
            (handler, extra_args, extra_kwargs, "on"))

        async def wrapper(wid, *args):
            resolved = [self._session._resolve_return(a) for a in args]
            result = handler(*resolved, *extra_args, **extra_kwargs)
            if hasattr(result, "__await__"):
                await result
        await self._session._listen(self._wid, action, wrapper)

    async def add_callback(self, action, handler, *extra_args, **extra_kwargs):
        """Register a callback. The handler receives
        ``(widget, *callback_args, *extra_args, **extra_kwargs)``.
        Handler can be sync or async.
        Multiple handlers can be registered for the same action."""
        # Store for reconstruction
        self._registered_callbacks.setdefault(action, []).append(
            (handler, extra_args, extra_kwargs, "add_callback"))

        async def wrapper(wid, *args):
            resolved = [self._session._resolve_return(a) for a in args]
            result = handler(self, *resolved, *extra_args, **extra_kwargs)
            if hasattr(result, "__await__"):
                await result
        await self._session._listen(self._wid, action, wrapper)

    @staticmethod
    def to_data_uri(path):
        """Convert a local file path to a ``data:`` URI.

        Reads the file, base64-encodes its contents, and returns a
        string like ``data:image/png;base64,iVBOR...`` that can be
        passed directly to methods such as ``set_image()`` or
        ``set_icon()``.

        Parameters
        ----------
        path : str
            Path to a local file.

        Returns
        -------
        str
            A data URI containing the file contents.
        """
        mime, _ = mimetypes.guess_type(path)
        if mime is None:
            mime = 'application/octet-stream'
        with open(path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('ascii')
        return f"data:{mime};base64,{data}"

    # Keep private alias for internal use
    _to_data_uri = to_data_uri

    async def add_cursor(self, name, url, hotspot_x, hotspot_y, size=None):
        """Register a named custom cursor. If url is a local file path
        it is read and converted to a data URI before sending."""
        if os.path.isfile(url):
            url = self._to_data_uri(url)
        return await self._call("add_cursor", name, url, hotspot_x, hotspot_y, size)

    async def destroy(self):
        """Destroy this widget: tear it down on the JS side and drop it
        from the Python-side registry so it can be garbage-collected."""
        # Remove from parent's children list
        if self._parent is not None:
            self._parent._children = [
                entry for entry in self._parent._children if entry[0] is not self
            ]
            self._parent = None
        try:
            await self._call("destroy")
        finally:
            self._session._widget_map.pop(self._wid, None)

    def __repr__(self):
        return f"<{self._js_class} wid={self._wid}>"


def _resolve_kwargs(method_name, param_names, args, kwargs):
    """Merge kwargs into positional args based on param_names.

    When the last declared param is ``"options"``, any remaining kwargs
    are bundled into a dict for that parameter (e.g.
    ``add_widget(child, title="Tab 1")`` becomes
    ``add_widget(child, {"title": "Tab 1"})``).
    """
    if not kwargs:
        return args
    merged = list(args)
    for i, name in enumerate(param_names):
        if i < len(merged):
            continue
        if name in kwargs:
            merged.append(kwargs.pop(name))
        else:
            break
    if kwargs and param_names and param_names[-1] == "options":
        # Bundle remaining kwargs into the options dict
        opts_idx = len(param_names) - 1
        if opts_idx < len(merged) and isinstance(merged[opts_idx], dict):
            merged[opts_idx] = {**merged[opts_idx], **kwargs}
        elif opts_idx < len(merged) and isinstance(merged[opts_idx], str):
            # String in options slot (e.g. add_action("text", toggle=True))
            # — convert to dict like the JS side does
            merged[opts_idx] = {"text": merged[opts_idx], **kwargs}
        else:
            while len(merged) < opts_idx:
                merged.append(None)
            if opts_idx < len(merged) and merged[opts_idx] is None:
                merged[opts_idx] = dict(kwargs)
            else:
                merged.append(dict(kwargs))
        kwargs.clear()
    if kwargs:
        unknown = ", ".join(sorted(kwargs))
        raise TypeError(
            f"{method_name}() got unexpected keyword arguments: {unknown}")
    return tuple(merged)


def _make_setter(method_name, param_names, state_key):
    """Create an async method that stores state locally and sends to the browser."""
    async def method(self, *args, **kwargs):
        args = _resolve_kwargs(method_name, param_names, args, kwargs)
        if len(args) == 1:
            self._state[state_key] = args[0]
        else:
            self._state[state_key] = args
        return await self._call(method_name, *args)
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    params = ", ".join(param_names)
    method.__doc__ = f"{method_name}({params})"
    return method


def _make_fixed_setter(method_name, state_key, fixed_value):
    """Create a no-arg async method that sets a fixed state value (show/hide)."""
    async def method(self):
        self._state[state_key] = fixed_value
        return await self._call(method_name)
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    method.__doc__ = f"{method_name}()"
    return method


def _make_getter(method_name, state_key):
    """Create a method that returns from local state (sync, no round-trip)."""
    def method(self):
        return self._state.get(state_key)
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    method.__doc__ = f"{method_name}() -> value from local state"
    return method


def _make_child_method(method_name, param_names, child_type):
    """Create an async method that tracks parent-child relationships."""
    is_replay = method_name in REPLAY_METHODS

    if child_type == "remove_all":
        async def method(self, *args, **kwargs):
            args = _resolve_kwargs(method_name, param_names, args, kwargs)
            # Detach all children
            roots = self._session._root_widgets
            for child, _, _ in self._children:
                child._parent = None
                if child not in roots:
                    roots.append(child)
            self._children = []
            return await self._call(method_name, *args)
        method.__name__ = method_name
        method.__qualname__ = f"Widget.{method_name}"
        params = ", ".join(param_names)
        method.__doc__ = f"{method_name}({params})"
        return method

    # Find which positional arg is the child widget
    child_idx = param_names.index("child") if "child" in param_names else 0

    async def method(self, *args, **kwargs):
        args = _resolve_kwargs(method_name, param_names, args, kwargs)
        child = args[child_idx]
        extra_args = args[:child_idx] + args[child_idx + 1:]

        if isinstance(child, Widget):
            if child_type == "remove":
                # Remove child from parent tracking
                self._children = [
                    (c, ea, mn) for c, ea, mn in self._children
                    if c is not child]
                child._parent = None
                # Child becomes a root again
                roots = self._session._root_widgets
                if child not in roots:
                    roots.append(child)
            elif child_type == "single":
                for old_child, _, _ in self._children:
                    old_child._parent = None
                    roots = self._session._root_widgets
                    if old_child not in roots:
                        roots.append(old_child)
                self._children = [(child, extra_args, method_name)]
            else:
                self._children.append((child, extra_args, method_name))
            if child_type != "remove":
                child._parent = self
                try:
                    self._session._root_widgets.remove(child)
                except ValueError:
                    pass
        elif is_replay:
            pass  # recorded after _call below

        result = await self._call(method_name, *args)

        # No browser connected — create a local proxy widget so the
        # caller can keep building the tree (e.g. menu.add_name(...)
        # returns a Menu/MenuAction proxy).
        if result is None and is_replay:
            ret_cls = FACTORY_RETURN_TYPES.get(
                (self._js_class, method_name))
            if ret_cls:
                session = self._session
                proxy_wid = session._next_wid
                session._next_wid += 1
                cls = session._widget_classes.get(ret_cls, Widget)
                result = cls._from_existing(session, proxy_wid, ret_cls)
                session._widget_map[proxy_wid] = result

        if (isinstance(result, Widget) and isinstance(child, Widget)
                and result is not child):
            result._child_content = child

        if is_replay and not isinstance(child, Widget):
            self._replay_calls.append((method_name, args, result))

        return result
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    params = ", ".join(param_names)
    method.__doc__ = f"{method_name}({params})"
    return method


def _make_action(method_name, param_names):
    """Create an async fire-and-forget method."""
    is_replay = method_name in REPLAY_METHODS
    select_key = CHILD_SELECT_METHODS.get(method_name)

    async def method(self, *args, **kwargs):
        args = _resolve_kwargs(method_name, param_names, args, kwargs)
        if select_key and args and isinstance(args[0], Widget):
            for i, (ch, _, _) in enumerate(self._children):
                if ch is args[0]:
                    self._state[select_key] = i
                    break
        result = await self._call(method_name, *args)
        if is_replay:
            self._replay_calls.append((method_name, args, result))
        return result
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    params = ", ".join(param_names)
    method.__doc__ = f"{method_name}({params})"
    return method


def _make_clear(method_name, widget_name):
    """Create an async clear() method that resets tracked state keys."""
    reset_keys = CLEAR_RESETS.get(widget_name, [])

    async def method(self):
        for key in reset_keys:
            self._state.pop(key, None)
        return await self._call("clear")
    method.__name__ = "clear"
    method.__qualname__ = f"Widget.clear"
    method.__doc__ = "clear()"
    return method


def _make_js_only(method_name, param_names):
    """Create an async method that passes through to the browser."""
    async def method(self, *args, **kwargs):
        args = _resolve_kwargs(method_name, param_names, args, kwargs)
        return await self._call(method_name, *args)
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    params = ", ".join(param_names)
    method.__doc__ = f"{method_name}({params}) [browser-only]"
    return method


def _add_item_list_methods(attrs, item_cfg, all_methods):
    """Override action methods to also track an item list in _state."""
    key = item_cfg["key"]
    append_name = item_cfg.get("append")
    insert_name = item_cfg.get("insert")
    delete_name = item_cfg.get("delete")

    if append_name and append_name in all_methods:
        param_names = all_methods[append_name]
        def make_append(mn, pn):
            async def method(self, *args, **kwargs):
                args = _resolve_kwargs(mn, pn, args, kwargs)
                items = self._state.setdefault(key, [])
                items.append(args[0])
                return await self._call(mn, *args)
            method.__name__ = mn
            return method
        attrs[append_name] = make_append(append_name, param_names)

    if insert_name and insert_name in all_methods:
        param_names = all_methods[insert_name]
        def make_insert(mn, pn):
            async def method(self, *args, **kwargs):
                args = _resolve_kwargs(mn, pn, args, kwargs)
                items = self._state.setdefault(key, [])
                text, idx = args[0], args[1] if len(args) > 1 else len(items)
                items.insert(idx, text)
                return await self._call(mn, *args)
            method.__name__ = mn
            return method
        attrs[insert_name] = make_insert(insert_name, param_names)

    if delete_name and delete_name in all_methods:
        param_names = all_methods[delete_name]
        def make_delete(mn, pn):
            async def method(self, *args, **kwargs):
                args = _resolve_kwargs(mn, pn, args, kwargs)
                items = self._state.get(key, [])
                val = args[0]
                if isinstance(val, int):
                    if 0 <= val < len(items):
                        items.pop(val)
                else:
                    # Delete by value (e.g. delete_alpha takes text)
                    try:
                        items.remove(val)
                    except ValueError:
                        pass
                return await self._call(mn, *args)
            method.__name__ = mn
            return method
        attrs[delete_name] = make_delete(delete_name, param_names)


def _add_tree_view_methods(attrs, all_methods):
    """Override expand/collapse/sort methods to track state for TreeView/TableView."""

    if "sort_by_column" in all_methods:
        param_names = all_methods["sort_by_column"]
        async def sort_method(self, *args, **kwargs):
            args = _resolve_kwargs("sort_by_column", param_names, args, kwargs)
            col = args[0] if args else 0
            asc = args[1] if len(args) > 1 else True
            self._state["_sort"] = (col, asc)
            return await self._call("sort_by_column", *args)
        sort_method.__name__ = "sort_by_column"
        attrs["sort_by_column"] = sort_method

    if "expand_item" in all_methods:
        param_names = all_methods["expand_item"]
        async def expand_item_method(self, *args, **kwargs):
            args = _resolve_kwargs("expand_item", param_names, args, kwargs)
            path = args[0] if args else None
            if path is not None:
                key = tuple(path) if isinstance(path, list) else path
                expanded = self._state.setdefault("_expanded_paths", set())
                expanded.add(key)
                collapsed = self._state.get("_collapsed_paths")
                if collapsed is not None and collapsed != "_all":
                    collapsed.discard(key)
            return await self._call("expand_item", *args)
        expand_item_method.__name__ = "expand_item"
        attrs["expand_item"] = expand_item_method

    if "collapse_item" in all_methods:
        param_names = all_methods["collapse_item"]
        async def collapse_item_method(self, *args, **kwargs):
            args = _resolve_kwargs("collapse_item", param_names, args, kwargs)
            path = args[0] if args else None
            if path is not None:
                key = tuple(path) if isinstance(path, list) else path
                expanded = self._state.get("_expanded_paths")
                if expanded is not None:
                    expanded.discard(key)
                collapsed = self._state.setdefault("_collapsed_paths", set())
                if collapsed != "_all":
                    collapsed.add(key)
            return await self._call("collapse_item", *args)
        collapse_item_method.__name__ = "collapse_item"
        attrs["collapse_item"] = collapse_item_method

    if "expand_all" in all_methods:
        async def expand_all_method(self):
            self._state.pop("_collapsed_paths", None)
            self._state["_expanded_paths"] = "_all"
            return await self._call("expand_all")
        expand_all_method.__name__ = "expand_all"
        attrs["expand_all"] = expand_all_method

    if "collapse_all" in all_methods:
        async def collapse_all_method(self):
            self._state["_collapsed_paths"] = "_all"
            self._state.pop("_expanded_paths", None)
            return await self._call("collapse_all")
        collapse_all_method.__name__ = "collapse_all"
        attrs["collapse_all"] = collapse_all_method


def _init_params(pos_names, opt_names):
    """Build the parameter string for the generated __init__."""
    params = ["self", "session"]
    for name in pos_names:
        params.append(f"{name}=None")
    if opt_names:
        params.append("*")
        for name in opt_names:
            params.append(f"{name}=None")
    params.append("**kwargs")
    return ", ".join(params)


def _init_body(pos_names, opt_names):
    """Build the body of the generated __init__."""
    lines = []

    # Collect positional args (trailing Nones are stripped later in
    # Widget.__init__ only when no options dict follows)
    if pos_names:
        for name in pos_names:
            lines.append(f"_pos.append({name})")
    else:
        lines.append("_pos = []")

    # Merge options into kwargs
    for name in opt_names:
        lines.append(f"if {name} is not None:")
        lines.append(f"    kwargs['{name}'] = {name}")

    lines.append("super(_cls, self).__init__(session, *_pos, **kwargs)")
    return "\n    ".join(lines)


def build_widget_class(js_class, defn):
    """Build an async stateful Widget subclass from a definition."""
    attrs = {}

    # Collect ALL method names (base + per-widget) for classification
    base = defn.get("base")
    if base == "container":
        base_methods = CONTAINER_METHODS
    elif base == "callback":
        base_methods = CALLBACK_METHODS
    else:
        base_methods = WIDGET_METHODS
    all_methods = dict(base_methods)
    all_methods.update(defn.get("methods", {}))

    # Generate base methods
    for method_name, param_names in base_methods.items():
        if method_name in ("destroy", "add_cursor"):
            continue
        _add_classified_method(attrs, method_name, param_names,
                               all_methods, js_class)

    # Generate per-widget methods (may override base)
    for method_name, param_names in defn.get("methods", {}).items():
        _add_classified_method(attrs, method_name, param_names,
                               all_methods, js_class)

    # Add error stubs for unsupported methods
    for (wc, mn), msg in UNSUPPORTED_METHODS.items():
        if wc == js_class:
            def _make_unsupported(name, message):
                def method(self, *args, **kwargs):
                    raise NotImplementedError(message)
                method.__name__ = name
                return method
            attrs[mn] = _make_unsupported(mn, msg)

    # Override action methods that need to track an item list
    item_cfg = ITEM_LIST_CONFIG.get(js_class)
    if item_cfg:
        _add_item_list_methods(attrs, item_cfg, all_methods)

    # Override expand/collapse/sort for tree/table widgets
    if js_class in TREE_VIEW_WIDGETS:
        _add_tree_view_methods(attrs, all_methods)

    # Generate __init__ with named parameters
    pos_names = defn.get("args", [])
    opt_names = defn.get("options", [])

    cls = type(js_class, (Widget,), attrs)
    cls._js_class_name = js_class
    cls._defn = defn

    # Create __init__ with proper signature via exec
    ns = {"_cls": cls, "super": super}
    # Need _pos initialization before the body appends to it
    body_prefix = "_pos = []\n    " if pos_names else ""
    exec_src = f"""
def __init__({_init_params(pos_names, opt_names)}):
    {body_prefix}{_init_body(pos_names, opt_names)}
"""
    exec(exec_src, ns)
    cls.__init__ = ns["__init__"]

    return cls


def _add_classified_method(attrs, method_name, param_names,
                           all_methods, widget_name):
    """Classify a method and add the appropriate implementation to attrs."""
    category, info = classify_method(method_name, param_names, all_methods)

    if category == SETTER:
        if method_name in FIXED_SETTERS:
            state_key, fixed_value = FIXED_SETTERS[method_name]
            attrs[method_name] = _make_fixed_setter(
                method_name, state_key, fixed_value)
        else:
            attrs[method_name] = _make_setter(
                method_name, param_names, info)

    elif category == GETTER:
        attrs[method_name] = _make_getter(method_name, info)

    elif category == CHILD:
        child_type = info
        attrs[method_name] = _make_child_method(
            method_name, param_names, child_type)

    elif category == ACTION:
        if method_name == "clear":
            attrs[method_name] = _make_clear(
                method_name, widget_name)
        else:
            attrs[method_name] = _make_action(method_name, param_names)

    elif category == JS_ONLY:
        attrs[method_name] = _make_js_only(method_name, param_names)


def build_all_widget_classes():
    """Build all widget classes from definitions. Returns a dict of name -> class."""
    classes = {}
    for js_class, defn in WIDGETS.items():
        classes[js_class] = build_widget_class(js_class, defn)
    return classes
