"""
Asynchronous base Widget class and widget class factory.
"""

import base64
import mimetypes
import os

from pgwidgets.defs import WIDGETS, CALLBACK_METHODS, WIDGET_METHODS, CONTAINER_METHODS


class Widget:
    """Base class for all async widget wrappers."""

    def __init__(self, session, wid, js_class):
        self._session = session
        self._wid = wid
        self._js_class = js_class

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
        return await self._session._call(self._wid, method, *resolved)

    async def on(self, action, handler, *extra_args, **extra_kwargs):
        """Register a callback. The handler receives
        ``(*callback_args, *extra_args, **extra_kwargs)`` -- no widget arg.
        Handler can be sync or async."""
        async def wrapper(wid, *args):
            resolved = [self._session._resolve_return(a) for a in args]
            result = handler(*resolved, *extra_args, **extra_kwargs)
            if hasattr(result, "__await__"):
                await result
        await self._session._listen(self._wid, action, wrapper)

    async def add_callback(self, action, handler, *extra_args, **extra_kwargs):
        """Register a callback. The handler receives
        ``(widget, *callback_args, *extra_args, **extra_kwargs)``.
        Handler can be sync or async."""
        async def wrapper(wid, *args):
            resolved = [self._session._resolve_return(a) for a in args]
            result = handler(self, *resolved, *extra_args, **extra_kwargs)
            if hasattr(result, "__await__"):
                await result
        await self._session._listen(self._wid, action, wrapper)

    @staticmethod
    def _to_data_uri(path):
        """Convert a file path to a data URI."""
        mime, _ = mimetypes.guess_type(path)
        if mime is None:
            mime = 'application/octet-stream'
        with open(path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('ascii')
        return f"data:{mime};base64,{data}"

    async def add_cursor(self, name, url, hotspot_x, hotspot_y, size=None):
        """Register a named custom cursor. If url is a local file path
        it is read and converted to a data URI before sending."""
        if os.path.isfile(url):
            url = self._to_data_uri(url)
        return await self._call("add_cursor", name, url, hotspot_x, hotspot_y, size)

    async def destroy(self):
        """Destroy this widget: tear it down on the JS side and drop it
        from the Python-side registry so it can be garbage-collected."""
        try:
            await self._call("destroy")
        finally:
            self._session._widget_map.pop(self._wid, None)

    def __repr__(self):
        return f"<{self._js_class} wid={self._wid}>"


def _make_method(method_name, param_names):
    """Create an async method that calls through to the JS widget.

    The generated method accepts positional args and keyword args matching
    the declared parameter names in param_names. Missing trailing args are
    simply omitted — the JS side handles its own default values.
    """
    async def method(self, *args, **kwargs):
        if kwargs:
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
            args = tuple(merged)
        return await self._call(method_name, *args)
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    params = ", ".join(param_names)
    method.__doc__ = f"{method_name}({params})"
    return method


def build_widget_class(js_class, defn):
    """Build an async Widget subclass from a definition."""
    attrs = {}

    # Base methods (WIDGET_METHODS, plus get_children for containers).
    # Applied first so per-widget methods can override.
    base = defn.get("base")
    if base == "container":
        base_methods = CONTAINER_METHODS
    elif base == "callback":
        base_methods = CALLBACK_METHODS
    else:
        base_methods = WIDGET_METHODS
    for method_name, param_names in base_methods.items():
        # destroy() is defined explicitly on the Widget base class so it
        # can also drop the wrapper from the Python-side registry.
        if method_name in ("destroy", "add_cursor"):
            continue
        attrs[method_name] = _make_method(method_name, param_names)

    # Per-widget methods override base methods with the same name.
    for method_name, param_names in defn.get("methods", {}).items():
        attrs[method_name] = _make_method(method_name, param_names)

    cls = type(js_class, (Widget,), attrs)
    cls._js_class_name = js_class
    cls._defn = defn
    return cls


def build_all_widget_classes():
    """Build all widget classes from definitions. Returns a dict of name -> class."""
    classes = {}
    for js_class, defn in WIDGETS.items():
        classes[js_class] = build_widget_class(js_class, defn)
    return classes
