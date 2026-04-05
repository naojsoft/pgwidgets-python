"""
Synchronous base Widget class and widget class factory.
"""

from pgwidgets.defs import WIDGETS, WIDGET_METHODS, CONTAINER_METHODS


class Widget:
    """Base class for all synchronous widget wrappers."""

    def __init__(self, app, wid, js_class):
        self._app = app
        self._wid = wid
        self._js_class = js_class

    @property
    def wid(self):
        return self._wid

    def _call(self, method, *args):
        """Call a method on the JS widget."""
        resolved = [self._app._resolve_arg(a) for a in args]
        return self._app._call(self._wid, method, *resolved)

    def on(self, action, handler, *extra_args, **extra_kwargs):
        """Register a callback. The handler receives
        (*callback_args, *extra_args, **extra_kwargs) — no widget arg."""
        def wrapper(wid, *args):
            resolved = [self._app._resolve_return(a) for a in args]
            handler(*resolved, *extra_args, **extra_kwargs)
        self._app._listen(self._wid, action, wrapper)

    def add_callback(self, action, handler, *extra_args, **extra_kwargs):
        """Register a callback. The handler receives
        (widget, *callback_args, *extra_args, **extra_kwargs)."""
        def wrapper(wid, *args):
            resolved = [self._app._resolve_return(a) for a in args]
            handler(self, *resolved, *extra_args, **extra_kwargs)
        self._app._listen(self._wid, action, wrapper)

    # -- Common Widget methods --

    def get_element(self):
        return self._call("get_element")

    def set_border_width(self, width):
        self._call("set_border_width", width)

    def set_border_color(self, color):
        self._call("set_border_color", color)

    def resize(self, width, height):
        self._call("resize", width, height)

    def get_size(self):
        return self._call("get_size")

    def set_padding(self, padding):
        self._call("set_padding", padding)

    def set_font(self, font, size=None, weight=None, style=None):
        self._call("set_font", font, size, weight, style)

    def set_enabled(self, tf):
        self._call("set_enabled", tf)

    def get_enabled(self):
        return self._call("get_enabled")

    def show(self):
        self._call("show")

    def hide(self):
        self._call("hide")

    def is_visible(self):
        return self._call("is_visible")

    def __repr__(self):
        return f"<{self._js_class} wid={self._wid}>"


def _make_method(method_name, param_names):
    """Create a method that calls through to the JS widget."""
    def method(self, *args):
        return self._call(method_name, *args)
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    params = ", ".join(param_names)
    method.__doc__ = f"{method_name}({params})"
    return method


def build_widget_class(js_class, defn):
    """Build a synchronous Widget subclass from a definition."""
    attrs = {}

    # Add specific methods from the definition
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
