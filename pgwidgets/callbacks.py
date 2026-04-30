"""
Callback registration mixin for Python-side utility classes.

Provides the same callback API as ``pgwidgets.sync.Widget`` /
``pgwidgets.async_.Widget`` (``add_callback``, ``on``, ``make_callback``,
etc.) so that composite/utility classes that aren't backed by a JS
widget can still expose handler registration to user code.

Typical use::

    from pgwidgets.callbacks import Callbacks

    class MyTool(Callbacks):
        def __init__(self):
            super().__init__()
            self.enable_callback("done")

        def do_work(self):
            ...
            self.make_callback("done", result)

    tool = MyTool()
    tool.add_callback("done", lambda obj, result: ...)   # widget-arg style
    tool.on("done", lambda result: ...)                  # plain style

The two registration methods exist to mirror Widget's two styles:
``add_callback`` prepends the source object to the args; ``on`` does not.
"""

import traceback


class Callbacks:
    """Base class providing callback registration and dispatch."""

    def __init__(self):
        # action -> list of (handler, extra_args, extra_kwargs, style)
        self._cb = {}

    # -- Registration --------------------------------------------------

    def enable_callback(self, action):
        """Declare that *action* is a valid callback name on this object."""
        self._cb.setdefault(action, [])

    def has_callback(self, action):
        """Return True if *action* has been enabled."""
        return action in self._cb

    def add_callback(self, action, handler, *extra_args, **extra_kwargs):
        """Register a handler for *action*.

        Handler is invoked as
        ``handler(self, *callback_args, *extra_args, **extra_kwargs)``.
        """
        self._cb.setdefault(action, []).append(
            (handler, extra_args, extra_kwargs, "add_callback"))

    def on(self, action, handler, *extra_args, **extra_kwargs):
        """Register a handler for *action* without the source-object arg.

        Handler is invoked as
        ``handler(*callback_args, *extra_args, **extra_kwargs)``.
        """
        self._cb.setdefault(action, []).append(
            (handler, extra_args, extra_kwargs, "on"))

    def remove_callback(self, action, handler):
        """Remove all entries for *action* whose handler is *handler*."""
        if action not in self._cb:
            return
        self._cb[action] = [
            entry for entry in self._cb[action]
            if entry[0] is not handler
        ]

    def clear_callback(self, action):
        """Remove all handlers registered for *action*."""
        if action in self._cb:
            self._cb[action] = []

    # -- Dispatch ------------------------------------------------------

    def make_callback(self, action, *args):
        """Invoke every handler registered for *action*.  Exceptions in
        one handler are logged but don't prevent the rest from running."""
        for handler, extra_args, extra_kwargs, style in list(
                self._cb.get(action, [])):
            try:
                if style == "on":
                    handler(*args, *extra_args, **extra_kwargs)
                else:
                    handler(self, *args, *extra_args, **extra_kwargs)
            except Exception:
                traceback.print_exc()
