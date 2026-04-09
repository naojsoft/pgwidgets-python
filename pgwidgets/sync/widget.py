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

    @property
    def app(self):
        """The Application this widget belongs to."""
        return self._app

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

    def destroy(self):
        """Destroy this widget: tear it down on the JS side and drop it
        from the Python-side registry so it can be garbage-collected."""
        try:
            self._call("destroy")
        finally:
            self._app._widget_map.pop(self._wid, None)

    def __repr__(self):
        return f"<{self._js_class} wid={self._wid}>"


def _make_method(method_name, param_names):
    """Create a method that calls through to the JS widget.

    The generated method accepts positional args and keyword args matching
    the declared parameter names in param_names. Missing trailing args are
    simply omitted — the JS side handles its own default values.
    """
    def method(self, *args, **kwargs):
        if kwargs:
            # Remap kwargs to positional order defined by param_names.
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
        return self._call(method_name, *args)
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    params = ", ".join(param_names)
    method.__doc__ = f"{method_name}({params})"
    return method


def build_widget_class(js_class, defn):
    """Build a synchronous Widget subclass from a definition."""
    attrs = {}

    # Base methods (WIDGET_METHODS, plus get_children for containers).
    # Applied first so per-widget methods can override.
    base_methods = CONTAINER_METHODS if defn.get("base") == "container" \
        else WIDGET_METHODS
    for method_name, param_names in base_methods.items():
        # destroy() is defined explicitly on the Widget base class so it
        # can also drop the wrapper from the Python-side registry.
        if method_name == "destroy":
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
