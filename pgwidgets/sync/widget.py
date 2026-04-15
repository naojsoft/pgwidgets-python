"""
Synchronous stateful Widget class and widget class factory.

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
)


class Widget:
    """Base class for all synchronous widget wrappers.

    Stores local state so the Python side can serve as the source of
    truth for the UI.
    """

    def __init__(self, session, wid, js_class):
        self._session = session
        self._wid = wid
        self._js_class = js_class

        # State tracking
        self._state = {}               # state_key -> value(s)
        self._children = []            # list of (child_widget, args_tuple)
        self._parent = None            # parent widget or None
        self._constructor_args = ()    # positional args passed to JS constructor
        self._constructor_options = {} # options dict passed to JS constructor
        self._registered_callbacks = {}  # action -> (handler, extra_args, extra_kwargs, style)
        self._auto_sync_actions = set() # callbacks auto-listened for state sync
        self._replay_calls = []        # [(method, args, returned_widget)]

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

    def _call(self, method, *args):
        """Call a method on the JS widget."""
        if method in self._FILE_ARG_METHODS:
            args = tuple(self._resolve_file_arg(a) for a in args)
        resolved = [self._session._resolve_arg(a) for a in args]
        result = self._session._call(self._wid, method, *resolved)
        return self._session._resolve_return(result)

    def on(self, action, handler, *extra_args, **extra_kwargs):
        """Register a callback. The handler receives
        ``(*callback_args, *extra_args, **extra_kwargs)`` -- no widget arg."""
        # Store for reconstruction
        self._registered_callbacks[action] = (
            handler, extra_args, extra_kwargs, "on")

        def wrapper(wid, *args):
            resolved = [self._session._resolve_return(a) for a in args]
            handler(*resolved, *extra_args, **extra_kwargs)
        self._session._listen(self._wid, action, wrapper)

    def add_callback(self, action, handler, *extra_args, **extra_kwargs):
        """Register a callback. The handler receives
        ``(widget, *callback_args, *extra_args, **extra_kwargs)``."""
        # Store for reconstruction
        self._registered_callbacks[action] = (
            handler, extra_args, extra_kwargs, "add_callback")

        def wrapper(wid, *args):
            resolved = [self._session._resolve_return(a) for a in args]
            handler(self, *resolved, *extra_args, **extra_kwargs)
        self._session._listen(self._wid, action, wrapper)

    @staticmethod
    def _to_data_uri(path):
        """Convert a file path to a data URI."""
        mime, _ = mimetypes.guess_type(path)
        if mime is None:
            mime = 'application/octet-stream'
        with open(path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('ascii')
        return f"data:{mime};base64,{data}"

    def add_cursor(self, name, url, hotspot_x, hotspot_y, size=None):
        """Register a named custom cursor. If url is a local file path
        it is read and converted to a data URI before sending."""
        if os.path.isfile(url):
            url = self._to_data_uri(url)
        return self._call("add_cursor", name, url, hotspot_x, hotspot_y, size)

    def destroy(self):
        """Destroy this widget: tear it down on the JS side and drop it
        from the Python-side registry so it can be garbage-collected."""
        # Remove from parent's children list
        if self._parent is not None:
            self._parent._children = [
                entry for entry in self._parent._children if entry[0] is not self
            ]
            self._parent = None
        try:
            self._call("destroy")
        finally:
            self._session._widget_map.pop(self._wid, None)

    def __repr__(self):
        return f"<{self._js_class} wid={self._wid}>"


def _resolve_kwargs(method_name, param_names, args, kwargs):
    """Merge kwargs into positional args based on param_names."""
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
    if kwargs:
        unknown = ", ".join(sorted(kwargs))
        raise TypeError(
            f"{method_name}() got unexpected keyword arguments: {unknown}")
    return tuple(merged)


def _make_setter(method_name, param_names, state_key):
    """Create a method that stores state locally and sends to the browser."""
    def method(self, *args, **kwargs):
        args = _resolve_kwargs(method_name, param_names, args, kwargs)
        # Store state: single param -> store value, multiple -> store tuple
        if len(args) == 1:
            self._state[state_key] = args[0]
        else:
            self._state[state_key] = args
        return self._call(method_name, *args)
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    params = ", ".join(param_names)
    method.__doc__ = f"{method_name}({params})"
    return method


def _make_fixed_setter(method_name, state_key, fixed_value):
    """Create a no-arg method that sets a fixed state value (show/hide)."""
    def method(self):
        self._state[state_key] = fixed_value
        return self._call(method_name)
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    method.__doc__ = f"{method_name}()"
    return method


def _make_getter(method_name, state_key):
    """Create a method that returns from local state."""
    def method(self):
        return self._state.get(state_key)
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    method.__doc__ = f"{method_name}() -> value from local state"
    return method


def _make_child_method(method_name, param_names, child_type):
    """Create a method that tracks parent-child relationships."""
    is_replay = method_name in REPLAY_METHODS

    def method(self, *args, **kwargs):
        args = _resolve_kwargs(method_name, param_names, args, kwargs)
        # First arg is always the child widget
        child = args[0]
        extra_args = args[1:]

        if isinstance(child, Widget):
            if child_type == "single":
                # Remove old child's parent ref
                for old_child, _, _ in self._children:
                    old_child._parent = None
                    # Old child becomes a root again
                    roots = self._session._root_widgets
                    if old_child not in roots:
                        roots.append(old_child)
                self._children = [(child, extra_args, method_name)]
            else:
                self._children.append((child, extra_args, method_name))
            child._parent = self
            # Child is no longer a root
            try:
                self._session._root_widgets.remove(child)
            except ValueError:
                pass
        elif is_replay:
            # Non-Widget first arg (e.g. add_action(opts), add_name(text)):
            # record call for reconstruction replay.
            pass  # recorded after _call below

        result = self._call(method_name, *args)
        # If the JS side returned a new wrapper widget (e.g.
        # MDISubWindow), link it back to the content child so
        # move/resize callbacks can update the options dict used
        # for reconstruction.
        if (isinstance(result, Widget) and isinstance(child, Widget)
                and result is not child):
            result._child_content = child

        # Record factory call for replay during reconstruction
        if is_replay and not isinstance(child, Widget):
            self._replay_calls.append((method_name, args, result))

        return result
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    params = ", ".join(param_names)
    method.__doc__ = f"{method_name}({params})"
    return method


def _make_action(method_name, param_names):
    """Create a fire-and-forget method (same as old behavior)."""
    is_replay = method_name in REPLAY_METHODS
    select_key = CHILD_SELECT_METHODS.get(method_name)

    def method(self, *args, **kwargs):
        args = _resolve_kwargs(method_name, param_names, args, kwargs)
        # Track child selection by index (e.g. show_widget -> index)
        if select_key and args and isinstance(args[0], Widget):
            for i, (ch, _, _) in enumerate(self._children):
                if ch is args[0]:
                    self._state[select_key] = i
                    break
        result = self._call(method_name, *args)
        if is_replay:
            self._replay_calls.append((method_name, args, result))
        return result
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    params = ", ".join(param_names)
    method.__doc__ = f"{method_name}({params})"
    return method


def _make_clear(method_name, widget_name):
    """Create a clear() method that resets tracked state keys."""
    reset_keys = CLEAR_RESETS.get(widget_name, [])

    def method(self):
        for key in reset_keys:
            self._state.pop(key, None)
        return self._call("clear")
    method.__name__ = "clear"
    method.__qualname__ = f"Widget.clear"
    method.__doc__ = "clear()"
    return method


def _make_js_only(method_name, param_names):
    """Create a method that passes through to the browser.

    These methods query browser-side state that isn't tracked locally.
    They work when a browser is connected but return None otherwise.
    """
    def method(self, *args, **kwargs):
        args = _resolve_kwargs(method_name, param_names, args, kwargs)
        return self._call(method_name, *args)
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
            def method(self, *args, **kwargs):
                args = _resolve_kwargs(mn, pn, args, kwargs)
                items = self._state.setdefault(key, [])
                items.append(args[0])
                return self._call(mn, *args)
            method.__name__ = mn
            return method
        attrs[append_name] = make_append(append_name, param_names)

    if insert_name and insert_name in all_methods:
        param_names = all_methods[insert_name]
        def make_insert(mn, pn):
            def method(self, *args, **kwargs):
                args = _resolve_kwargs(mn, pn, args, kwargs)
                items = self._state.setdefault(key, [])
                text, idx = args[0], args[1] if len(args) > 1 else len(items)
                items.insert(idx, text)
                return self._call(mn, *args)
            method.__name__ = mn
            return method
        attrs[insert_name] = make_insert(insert_name, param_names)

    if delete_name and delete_name in all_methods:
        param_names = all_methods[delete_name]
        def make_delete(mn, pn):
            def method(self, *args, **kwargs):
                args = _resolve_kwargs(mn, pn, args, kwargs)
                items = self._state.get(key, [])
                idx = args[0]
                if 0 <= idx < len(items):
                    items.pop(idx)
                return self._call(mn, *args)
            method.__name__ = mn
            return method
        attrs[delete_name] = make_delete(delete_name, param_names)


def _add_tree_view_methods(attrs, all_methods):
    """Override expand/collapse/sort methods to track state for TreeView/TableView."""

    if "sort_by_column" in all_methods:
        param_names = all_methods["sort_by_column"]
        def sort_method(self, *args, **kwargs):
            args = _resolve_kwargs("sort_by_column", param_names, args, kwargs)
            col = args[0] if args else 0
            asc = args[1] if len(args) > 1 else True
            self._state["_sort"] = (col, asc)
            return self._call("sort_by_column", *args)
        sort_method.__name__ = "sort_by_column"
        attrs["sort_by_column"] = sort_method

    if "expand_item" in all_methods:
        param_names = all_methods["expand_item"]
        def expand_item_method(self, *args, **kwargs):
            args = _resolve_kwargs("expand_item", param_names, args, kwargs)
            path = args[0] if args else None
            if path is not None:
                collapsed = self._state.get("_collapsed_paths")
                if collapsed is not None:
                    key = tuple(path) if isinstance(path, list) else path
                    collapsed.discard(key)
            return self._call("expand_item", *args)
        expand_item_method.__name__ = "expand_item"
        attrs["expand_item"] = expand_item_method

    if "collapse_item" in all_methods:
        param_names = all_methods["collapse_item"]
        def collapse_item_method(self, *args, **kwargs):
            args = _resolve_kwargs("collapse_item", param_names, args, kwargs)
            path = args[0] if args else None
            if path is not None:
                collapsed = self._state.setdefault("_collapsed_paths", set())
                key = tuple(path) if isinstance(path, list) else path
                collapsed.add(key)
            return self._call("collapse_item", *args)
        collapse_item_method.__name__ = "collapse_item"
        attrs["collapse_item"] = collapse_item_method

    if "expand_all" in all_methods:
        def expand_all_method(self):
            self._state.pop("_collapsed_paths", None)
            return self._call("expand_all")
        expand_all_method.__name__ = "expand_all"
        attrs["expand_all"] = expand_all_method

    if "collapse_all" in all_methods:
        def collapse_all_method(self):
            # Mark all as collapsed — use sentinel value
            self._state["_collapsed_paths"] = "_all"
            return self._call("collapse_all")
        collapse_all_method.__name__ = "collapse_all"
        attrs["collapse_all"] = collapse_all_method


def build_widget_class(js_class, defn):
    """Build a synchronous stateful Widget subclass from a definition."""
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

    # Override action methods that need to track an item list
    item_cfg = ITEM_LIST_CONFIG.get(js_class)
    if item_cfg:
        _add_item_list_methods(attrs, item_cfg, all_methods)

    # Override expand/collapse/sort for tree/table widgets
    if js_class in TREE_VIEW_WIDGETS:
        _add_tree_view_methods(attrs, all_methods)

    cls = type(js_class, (Widget,), attrs)
    cls._js_class_name = js_class
    cls._defn = defn
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
        child_type = info  # "multi" or "single"
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
