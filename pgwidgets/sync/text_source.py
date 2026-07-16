"""Python-authoritative TextSource for the synchronous API.

Unlike most widgets (whose state is a handful of scalars), a text buffer
has rich structure -- content, live position refs, a tag table, cursor and
selection.  We keep the *authoritative* copy of all of that on the Python
side in a :class:`~pgwidgets.text_model.TextModel`, so the whole API works
before a browser is ever connected (the UI can be built up headless and
replayed on connect).  The browser is driven as a *view*: model changes are
pushed as offset-based operations through the render hooks, and are no-ops
(``_call`` returns None) until a browser attaches, at which point
``_reconstruct_model`` replays the full state.

Refs never cross the wire -- they are ordinary Python ``TextBufferRef``
objects owned by the local model.  (The in-situ / JS-only case, where the
browser is authoritative, is handled by the separate pgwidgets-js/pyodide
wrapper, not here.)

The class subclasses the *generated* TextSource proxy so it inherits all the
base-widget methods (show/hide/set_tooltip/get_size/...) and the widget
option setters (set_editable/set_wrap/scrolling); it overrides only the
methods that manipulate the text model.
"""

from pgwidgets.sync.widget import build_widget_class
from pgwidgets.defs import WIDGETS
from pgwidgets.text_model import TextModel


_GeneratedTextSource = build_widget_class("TextSource", WIDGETS["TextSource"])


class _BrowserTextModel(TextModel):
    """A TextModel whose render hooks push offset-based operations to the
    browser via the owning widget.  When no browser is connected the calls
    are no-ops, so the model is fully usable headless."""

    def __init__(self, widget):
        self._widget = widget
        super().__init__()

    def _push(self, method, *args):
        # _call round-trips when a browser is connected and is a no-op
        # returning None otherwise.
        self._widget._call(method, *args)

    # -- render hooks (see TextModel) --
    def _set_editor_text(self, text):
        self._push("set_text", text)

    def _replace_editor_range(self, start, end, new_text):
        # Drive the JS buffer by offset; pushUndo=False because the Python
        # model owns undo/redo.
        self._push("_replaceRange", start, end, new_text, {"pushUndo": False})

    def _apply_all_formats(self, region=None):
        # Push the current tag intervals; the JS side re-renders styling.
        # (Tag *definitions* are pushed by TextSource.create_tag.)
        self._push("_restoreTagIntervals", self._tag_intervals())

    def _apply_selection_to_editor(self):
        if self._sel_start == self._sel_end:
            self._push("_setCursorOffset", self._cursor)
        else:
            self._push("_setSelectionOffsets", self._sel_start, self._sel_end)

    def _refresh_icon_gutter(self):
        # TODO: render ref-anchored gutter icons in the browser.
        pass

    def _mark_clean(self):
        pass

    def _tag_intervals(self):
        return [{"name": t["name"], "start": t["start"], "end": t["end"]}
                for t in self._tags]


# Model methods delegated verbatim to self._model.  Refs in/out are the
# model's own TextBufferRefs; nothing here touches the wire.  These override
# the generated round-trip proxies of the same name.
_DELEGATED = (
    # content
    "get_length", "get_text", "get_text_range", "clear", "set_text",
    "insert_text", "delete_range",
    # refs
    "create_ref", "remove_ref", "create_named_ref", "get_named_ref",
    "remove_named_ref", "get_ref_start", "get_ref_end", "get_ref_bounds",
    "get_ref_line_start", "get_ref_line_end", "set_icon",
    # tags (create_tag handled explicitly to also push the tag definition)
    "remove_tag_def", "has_tag", "apply_tag", "remove_tag",
    "get_tags_at", "get_tags_range", "get_tag_region", "get_tag_regions",
    # find / replace
    "find", "find_all", "replace",
    # cursor / selection
    "get_cursor", "set_cursor", "has_selection", "get_selection_range",
    "get_selection_bounds", "set_selection_range",
    # undo / redo / dirty flag
    "can_undo", "can_redo", "undo", "redo", "get_modified", "mark_clean",
    # misc convenience
    "get_end_lineno", "clear_icons",
)

# Callback actions that are model-authoritative (fire from the Python model)
# rather than being browser events.
_MODEL_CALLBACKS = {"changed", "cursor-moved", "cursor_moved"}


class TextSource(_GeneratedTextSource):

    def __init__(self, session, *args, **kwargs):
        super().__init__(session, *args, **kwargs)
        # The authoritative model.  Seed its text from the initial value the
        # generated __init__ recorded (the JS side already has it from the
        # constructor, so no push).  Text/tags/cursor are reconstructed by
        # _reconstruct_model(), not by the generic state replay, so drop
        # 'text' from _state.
        self._model = _BrowserTextModel(self)
        text = self._state.get("text")
        self._model._text = "" if text is None else str(text)
        self._state.pop("text", None)

    def create_tag(self, name, attrs=None, **kwdargs):
        """Define a display tag locally and push its styling to the browser."""
        merged = {} if attrs is None else dict(attrs)
        merged.update(kwdargs)
        self._model.create_tag(name, merged)
        self._call("create_tag", name, merged)

    def scroll_to_ref(self, ref):
        """Scroll the view to a ref, addressed by its current offset."""
        self._call("_scrollToOffset", self._model._offset_of(ref))

    def scroll_to_lineno(self, lineno):
        """Scroll so that line ``lineno`` is visible."""
        self._call("_scrollToOffset",
                   self._model._offset_of_line_start(lineno))

    def scroll_to_end(self):
        """Scroll to the end of the buffer."""
        self._call("_scrollToOffset", self._model.get_length())

    def show_tooltip(self, text, x, y):
        """Show a hover tooltip (``text``) near viewport point (x, y), or
        hide it when ``text`` is empty.  Normally called from a handler of
        the 'tooltip' callback."""
        self._call("_showTooltip", text, x, y)

    # -- callbacks: 'changed'/'cursor_moved' are model-authoritative --
    def add_callback(self, action, handler, *extra_args, **extra_kwargs):
        if action in _MODEL_CALLBACKS:
            self._model.add_callback(
                self._model_cb_name(action),
                lambda _m, *a: handler(self, *a, *extra_args, **extra_kwargs))
            return
        super().add_callback(action, handler, *extra_args, **extra_kwargs)

    def on(self, action, handler, *extra_args, **extra_kwargs):
        if action in _MODEL_CALLBACKS:
            self._model.add_callback(
                self._model_cb_name(action),
                lambda _m, *a: handler(*a, *extra_args, **extra_kwargs))
            return
        super().on(action, handler, *extra_args, **extra_kwargs)

    @staticmethod
    def _model_cb_name(action):
        return "cursor-moved" if action in ("cursor_moved",
                                            "cursor-moved") else "changed"

    # -- reconstruction: push the full model state to a freshly-connected
    #    browser (called by Session._reconstruct_widget after the generic
    #    create/state/callback replay) --
    def _reconstruct_model(self):
        m = self._model
        self._call("set_text", m.get_text())
        for name, attrs in m._tag_defs.items():
            self._call("create_tag", name, attrs)
        intervals = m._tag_intervals()
        if intervals:
            self._call("_restoreTagIntervals", intervals)
        if m._sel_start != m._sel_end:
            self._call("_setSelectionOffsets", m._sel_start, m._sel_end)
        else:
            self._call("_setCursorOffset", m._cursor)


def _install_delegators():
    """Override the generated round-trip proxies with model-delegating
    methods (defined at class scope so ``hasattr(TextSource, name)`` holds)."""
    for _name in _DELEGATED:
        def _make(n):
            def method(self, *args, **kwargs):
                return getattr(self._model, n)(*args, **kwargs)
            method.__name__ = n
            method.__qualname__ = "TextSource." + n
            return method
        setattr(TextSource, _name, _make(_name))


_install_delegators()
