"""
Asynchronous base Widget class and widget class factory.
"""

from pgwidgets.defs import WIDGETS


class Widget:
    """Base class for all async widget wrappers."""

    def __init__(self, app, wid, js_class):
        self._app = app
        self._wid = wid
        self._js_class = js_class

    @property
    def wid(self):
        return self._wid

    async def _call(self, method, *args):
        """Call a method on the JS widget."""
        resolved = [self._app._resolve_arg(a) for a in args]
        return await self._app._call(self._wid, method, *resolved)

    async def on(self, action, handler):
        """Register a callback. The handler receives (*args) — no widget arg.
        Handler can be sync or async."""
        async def wrapper(wid, *args):
            resolved = [self._app._resolve_return(a) for a in args]
            result = handler(*resolved)
            if hasattr(result, "__await__"):
                await result
        await self._app._listen(self._wid, action, wrapper)

    async def add_callback(self, action, handler):
        """Register a callback. The handler receives (widget, *args).
        Handler can be sync or async."""
        async def wrapper(wid, *args):
            resolved = [self._app._resolve_return(a) for a in args]
            result = handler(self, *resolved)
            if hasattr(result, "__await__"):
                await result
        await self._app._listen(self._wid, action, wrapper)

    # -- Common Widget methods --

    async def get_element(self):
        return await self._call("get_element")

    async def set_border_width(self, width):
        await self._call("set_border_width", width)

    async def set_border_color(self, color):
        await self._call("set_border_color", color)

    async def resize(self, width, height):
        await self._call("resize", width, height)

    async def get_size(self):
        return await self._call("get_size")

    async def set_padding(self, padding):
        await self._call("set_padding", padding)

    async def set_font(self, font, size=None, weight=None, style=None):
        await self._call("set_font", font, size, weight, style)

    async def set_enabled(self, tf):
        await self._call("set_enabled", tf)

    async def get_enabled(self):
        return await self._call("get_enabled")

    async def show(self):
        await self._call("show")

    async def hide(self):
        await self._call("hide")

    async def is_visible(self):
        return await self._call("is_visible")

    def __repr__(self):
        return f"<{self._js_class} wid={self._wid}>"


def _make_method(method_name, param_names):
    """Create an async method that calls through to the JS widget."""
    async def method(self, *args):
        return await self._call(method_name, *args)
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    params = ", ".join(param_names)
    method.__doc__ = f"{method_name}({params})"
    return method


def build_widget_class(js_class, defn):
    """Build an async Widget subclass from a definition."""
    attrs = {}
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
