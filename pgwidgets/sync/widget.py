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

from pgwidgets import tree_model
from pgwidgets.defs import WIDGETS, CALLBACK_METHODS, WIDGET_METHODS, CONTAINER_METHODS
from pgwidgets.method_types import (
    classify_method, SETTER, GETTER, CHILD, ACTION, JS_ONLY,
    CHILD_METHODS as CHILD_METHOD_TYPES,
    FIXED_SETTERS, CLEAR_RESETS, ITEM_LIST_CONFIG,
    REPLAY_METHODS, CHILD_SELECT_METHODS, TREE_VIEW_WIDGETS,
    STATE_SYNC_CALLBACKS, STATE_SYNC_REQUIRES_OPTION,
    WIDGET_CALLBACK_SYNC, CHILD_CLOSE_CALLBACKS,
    FACTORY_RETURN_TYPES, UNSUPPORTED_METHODS, CUSTOM_METHODS,
    STATE_DEFAULTS, STATE_KEY_DEFAULTS,
)


class Widget:
    """Base class for all synchronous widget wrappers.

    Subclasses are generated from widget definitions and have proper
    constructors with named parameters::

        btn = Button(session, "Click me", icon="path/to/icon.png")

    The first argument is always the session.  Remaining arguments
    match the widget definition's ``args`` and ``options``.

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
        # Actions we listen to passively for getter support
        # (e.g. 'resize' on every visual widget so get_size() returns
        # a current value), but that aren't in _auto_sync_actions and
        # therefore don't push to peers or replay on reconstruction.
        self._passive_sync_actions = set()
        # State keys the user explicitly set via a setter call.
        # Used during reconstruction to decide whether a state key
        # should be replayed: passively-captured callback state
        # (e.g. layout-determined size) is NOT in this set.
        self._user_set_state = set()
        self._replay_calls = []
        self._add_seq = 0  # insertion order across _children + _replay_calls

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

        # Allocate wid and create on JS side
        wid = session._create(js_class, *js_args)
        self._wid = wid
        self._stale = False
        session._widget_map[wid] = self

        # Store constructor info for reconstruction
        self._constructor_args = tuple(args[:len(pos_names)])
        self._constructor_options = dict(options)

        # Store constructor args as initial state (None means "not
        # provided" since generated __init__ defaults all args to None)
        for i, name in enumerate(pos_names):
            if i < len(args) and args[i] is not None:
                self._state[name] = args[i]
        for k, v in options.items():
            if v is not None:
                self._state[k] = v

        # Apply default state for keys not set by constructor
        for k, v in STATE_DEFAULTS.get(js_class, {}).items():
            self._state.setdefault(k, v)

        # Apply remaining kwargs as setter calls
        for k, v in kwargs.items():
            setter = f"set_{k}"
            if hasattr(self, setter):
                getattr(self, setter)(v)
            else:
                raise TypeError(
                    f"{js_class}() got unexpected keyword "
                    f"argument '{k}'")

        # Register auto-sync listeners
        self._register_auto_sync()

        # Track as root widget (may be reparented later)
        session._root_widgets.append(self)

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
        obj._passive_sync_actions = set()
        obj._user_set_state = set()
        obj._replay_calls = []
        obj._add_seq = 0
        obj._stale = False
        return obj

    def _register_auto_sync(self):
        """Register auto-sync listeners for state tracking and cross-browser sync."""
        defn = self._defn
        if defn is None:
            return
        session = self._session
        wid = self._wid
        js_class = self._js_class

        opt_names_set = set(defn.get("options", []))
        all_callbacks = defn.get("callbacks", [])

        # State-sync callbacks (move -> position, resize -> size).
        # For visual widgets we always *listen* so getters like
        # get_size() / get_position() can return current values.
        # But we only add the action to _auto_sync_actions — which
        # controls push-to-peers and replay-on-reconstruction — when
        # the widget actually opted in (e.g. via the 'resizable' option
        # or by declaring the callback in its defn).  This keeps
        # layout-determined sizes from being replayed as literal
        # resize() calls that would pin flex/expanding widgets.
        is_visual = defn.get("base") != "callback"
        for action in STATE_SYNC_CALLBACKS:
            req_opt = STATE_SYNC_REQUIRES_OPTION.get(action)
            opted_in = False
            if req_opt is not None:
                opted_in = req_opt in opt_names_set
            else:
                opted_in = action in all_callbacks
            # Visual widgets get the listen unconditionally for resize
            # (it's a universal base-class callback) and for any move
            # they declare.  Non-visual Callback-base objects get
            # nothing here.
            if not is_visual:
                continue
            if action == "resize" or opted_in:
                session._listen(wid, action, lambda wid, *a: None)
            if opted_in:
                self._auto_sync_actions.add(action)
            elif action == "resize":
                self._passive_sync_actions.add(action)

        # Per-widget-class state sync (e.g. Slider "activated" -> value)
        cls_sync = WIDGET_CALLBACK_SYNC.get(js_class, {})
        for action in cls_sync:
            if action not in self._auto_sync_actions:
                session._listen(wid, action, lambda wid, *a: None)
                self._auto_sync_actions.add(action)

        # Child-close callbacks (e.g. MDI page-close)
        for action in CHILD_CLOSE_CALLBACKS:
            if action in all_callbacks:
                session._listen(wid, action, lambda wid, *a: None)
                self._auto_sync_actions.add(action)

        # Tree/table state callbacks
        if js_class in TREE_VIEW_WIDGETS:
            for action in ("expanded", "collapsed", "sorted"):
                if action not in self._auto_sync_actions:
                    session._listen(wid, action, lambda wid, *a: None)
                    self._auto_sync_actions.add(action)

    @property
    def wid(self):
        return self._wid

    @property
    def session(self):
        """The Session this widget belongs to."""
        return self._session

    def batch(self):
        """Convenience for ``widget.session.batch()``.

        Batching is per session, not per widget, so updates to other
        widgets made inside the block ride along in the same message::

            with tree.batch():
                tree.set_cell(path, 'seeing', '1.4')
                status.set_text('updated')
        """
        return self._session.batch()

    @property
    def app(self):
        """The Application this widget belongs to."""
        return self._session.app

    def is_container(self):
        """Return True if this widget is a container (can hold children)."""
        defn = WIDGETS.get(self._js_class, {})
        return defn.get("base") == "container"

    def num_children(self):
        """Return the number of children in this container."""
        return len(self._children)

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

    def _log_error(self, fmt, *args):
        """Log an error via the session's logger.  Used for non-fatal
        JS-side errors so the message goes to wherever the application
        was configured to send its logs.  Wrapped in try/except so a
        misbehaving logger handler can never propagate back into the
        widget call chain."""
        try:
            self._session._logger.error(fmt, *args)
        except Exception:
            pass

    def _call(self, method, *args):
        """Call a method on the JS widget.

        If the JS side reports the widget as unknown (e.g. it was
        destroyed but Python still holds a reference), the widget is
        marked stale and ``None`` is returned so callers can continue
        rather than aborting their entire callback chain.  Subsequent
        calls on the stale widget short-circuit without a round-trip.
        """
        if self._stale:
            return None
        if method in self._FILE_ARG_METHODS:
            args = tuple(self._resolve_file_arg(a) for a in args)
        resolved = [self._session._resolve_arg(a) for a in args]
        try:
            result = self._session._call(self._wid, method, *resolved)
        except RuntimeError as e:
            msg = str(e)
            if msg.startswith("Unknown widget id"):
                # The widget itself is gone from the JS side (e.g. it
                # was destroyed but Python still holds a reference).
                # Mark stale so subsequent calls on this widget
                # short-circuit silently, and return None.
                self._stale = True
                self._log_error(
                    "%s wid=%s.%s: %s (widget marked stale)",
                    self._js_class, self._wid, method, msg)
                return None
            if msg.startswith("Unknown method"):
                # Only this method is missing on the JS side (e.g. the
                # browser is running an older build).  Don't mark the
                # widget stale — other methods on it may still work.
                self._log_error(
                    "%s wid=%s.%s: %s (skipped)",
                    self._js_class, self._wid, method, msg)
                return None
            raise
        return self._session._resolve_return(result)

    def on(self, action, handler, *extra_args, **extra_kwargs):
        """Register a callback. The handler receives
        ``(*callback_args, *extra_args, **extra_kwargs)`` -- no widget arg.
        Multiple handlers can be registered for the same action."""
        # Store for reconstruction
        self._registered_callbacks.setdefault(action, []).append(
            (handler, extra_args, extra_kwargs, "on"))

        def wrapper(wid, *args):
            resolved = [self._session._resolve_return(a) for a in args]
            handler(*resolved, *extra_args, **extra_kwargs)
        self._session._listen(self._wid, action, wrapper)

    def has_callback(self, action):
        """Return True if this widget supports the given callback action."""
        defn = self._defn
        if defn is None:
            return False
        return action in defn.get("callbacks", [])

    def add_callback(self, action, handler, *extra_args, **extra_kwargs):
        """Register a callback. The handler receives
        ``(widget, *callback_args, *extra_args, **extra_kwargs)``.
        Multiple handlers can be registered for the same action."""
        # Store for reconstruction
        self._registered_callbacks.setdefault(action, []).append(
            (handler, extra_args, extra_kwargs, "add_callback"))

        def wrapper(wid, *args):
            resolved = [self._session._resolve_return(a) for a in args]
            handler(self, *resolved, *extra_args, **extra_kwargs)
        self._session._listen(self._wid, action, wrapper)

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
    """Merge kwargs into positional args based on param_names.

    When the last declared param is ``"options"``, any remaining kwargs
    are bundled into a dict for that parameter (e.g.
    ``add_widget(child, title="Tab 1")`` becomes
    ``add_widget(child, {"title": "Tab 1"})``).

    Skipped-positional kwargs are supported: a call like
    ``set_color(fg='red')`` against ``param_names = ['bg', 'fg']``
    fills the omitted ``bg`` slot with ``None`` (the JS-side
    default) instead of erroring out.
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
            # Leave a placeholder so subsequent kwargs can land in
            # later positions.  The JS side reads omitted args as
            # null / default, which matches ``None`` here.
            merged.append(None)
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
    """Create a method that stores state locally and sends to the browser."""
    def method(self, *args, **kwargs):
        args = _resolve_kwargs(method_name, param_names, args, kwargs)
        # Store state: single param -> store value, multiple -> store tuple
        if len(args) == 1:
            self._state[state_key] = args[0]
        else:
            self._state[state_key] = args
        # Mark as user-set so reconstruction knows to replay this key
        # (callback-captured values for the same key don't get marked).
        self._user_set_state.add(state_key)
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
        self._user_set_state.add(state_key)
        return self._call(method_name)
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    method.__doc__ = f"{method_name}()"
    return method


def _make_getter(method_name, state_key, default=None):
    """Create a method that returns from local state."""
    def method(self):
        return self._state.get(state_key, default)
    method.__name__ = method_name
    method.__qualname__ = f"Widget.{method_name}"
    method.__doc__ = f"{method_name}() -> value from local state"
    return method


def _make_child_method(method_name, param_names, child_type):
    """Create a method that tracks parent-child relationships."""
    is_replay = method_name in REPLAY_METHODS

    if child_type == "remove_all":
        def method(self, *args, **kwargs):
            args = _resolve_kwargs(method_name, param_names, args, kwargs)
            # Detach all children
            roots = self._session._root_widgets
            for entry in self._children:
                entry[0]._parent = None
                if entry[0] not in roots:
                    roots.append(entry[0])
            self._children = []
            return self._call(method_name, *args)
        method.__name__ = method_name
        method.__qualname__ = f"Widget.{method_name}"
        params = ", ".join(param_names)
        method.__doc__ = f"{method_name}({params})"
        return method

    # Find which positional arg is the child widget
    child_idx = param_names.index("child") if "child" in param_names else 0

    def method(self, *args, **kwargs):
        args = _resolve_kwargs(method_name, param_names, args, kwargs)
        child = args[child_idx]
        extra_args = args[:child_idx] + args[child_idx + 1:]

        if isinstance(child, Widget):
            if child_type == "remove":
                # Remove child from parent tracking
                self._children = [
                    entry for entry in self._children
                    if entry[0] is not child]
                child._parent = None
                # Child becomes a root again
                roots = self._session._root_widgets
                if child not in roots:
                    roots.append(child)
            elif child_type == "single":
                # Remove old child's parent ref
                for entry in self._children:
                    old_child = entry[0]
                    old_child._parent = None
                    # Old child becomes a root again
                    roots = self._session._root_widgets
                    if old_child not in roots:
                        roots.append(old_child)
                self._children = [(child, extra_args, method_name, self._add_seq)]
                self._add_seq += 1
            else:
                self._children.append((child, extra_args, method_name, self._add_seq))
                self._add_seq += 1
            if child_type != "remove":
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

        # If the JS side returned a new wrapper widget (e.g.
        # MDISubWindow), link it back to the content child so
        # move/resize callbacks can update the options dict used
        # for reconstruction.
        if (isinstance(result, Widget) and isinstance(child, Widget)
                and result is not child):
            result._child_content = child

        # Record factory call for replay during reconstruction
        if is_replay and not isinstance(child, Widget):
            self._replay_calls.append((method_name, args, result, self._add_seq))
            self._add_seq += 1

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
            for i, entry in enumerate(self._children):
                if entry[0] is args[0]:
                    self._state[select_key] = i
                    break
        result = self._call(method_name, *args)
        if is_replay:
            self._replay_calls.append((method_name, args, result, self._add_seq))
            self._add_seq += 1
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

    def _auto_select_first_if_empty(self, was_empty, items):
        """If the list went from empty to one item AND the user hasn't
        explicitly called set_index, mirror the JS-side auto-selection
        in our local state so get_index/get_text return the right thing
        before any browser callback round-trips."""
        if not was_empty:
            return
        if "index" in self._state:
            return  # user already called set_index
        # The selected item is whichever is now at items[0] (insert_alpha
        # may have placed our text at 0, append_text always at 0 since
        # the list was empty before).
        self._state["index"] = 0
        self._state["text"] = items[0]

    if append_name and append_name in all_methods:
        param_names = all_methods[append_name]
        def make_append(mn, pn):
            def method(self, *args, **kwargs):
                args = _resolve_kwargs(mn, pn, args, kwargs)
                items = self._state.setdefault(key, [])
                was_empty = len(items) == 0
                items.append(args[0])
                _auto_select_first_if_empty(self, was_empty, items)
                return self._call(mn, *args)
            method.__name__ = mn
            return method
        attrs[append_name] = make_append(append_name, param_names)

    if insert_name and insert_name in all_methods:
        param_names = all_methods[insert_name]
        # If the insert method's only parameter is "text" (e.g.
        # ComboBox.insert_alpha), mirror the JS-side alpha-sort so the
        # local list matches the browser's order.  Otherwise treat the
        # second arg as an explicit insert index.
        alpha_sort = param_names == ["text"]
        def make_insert(mn, pn, alpha):
            def method(self, *args, **kwargs):
                args = _resolve_kwargs(mn, pn, args, kwargs)
                items = self._state.setdefault(key, [])
                was_empty = len(items) == 0
                text = args[0]
                if alpha:
                    idx = len(items)
                    for i, existing in enumerate(items):
                        if text < existing:
                            idx = i
                            break
                else:
                    idx = args[1] if len(args) > 1 else len(items)
                items.insert(idx, text)
                _auto_select_first_if_empty(self, was_empty, items)
                return self._call(mn, *args)
            method.__name__ = mn
            return method
        attrs[insert_name] = make_insert(insert_name, param_names, alpha_sort)

    if delete_name and delete_name in all_methods:
        param_names = all_methods[delete_name]
        def make_delete(mn, pn):
            def method(self, *args, **kwargs):
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
                key = tuple(path) if isinstance(path, list) else path
                expanded = self._state.setdefault("_expanded_paths", set())
                if expanded != "_all":
                    expanded.add(key)
                collapsed = self._state.get("_collapsed_paths")
                if collapsed is not None and collapsed != "_all":
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
                key = tuple(path) if isinstance(path, list) else path
                expanded = self._state.get("_expanded_paths")
                if expanded is not None and expanded != "_all":
                    expanded.discard(key)
                collapsed = self._state.setdefault("_collapsed_paths", set())
                if collapsed != "_all":
                    collapsed.add(key)
            return self._call("collapse_item", *args)
        collapse_item_method.__name__ = "collapse_item"
        attrs["collapse_item"] = collapse_item_method

    if "expand_all" in all_methods:
        def expand_all_method(self):
            self._state.pop("_collapsed_paths", None)
            self._state["_expanded_paths"] = "_all"
            return self._call("expand_all")
        expand_all_method.__name__ = "expand_all"
        attrs["expand_all"] = expand_all_method

    if "collapse_all" in all_methods:
        def collapse_all_method(self):
            self._state["_collapsed_paths"] = "_all"
            self._state.pop("_expanded_paths", None)
            return self._call("collapse_all")
        collapse_all_method.__name__ = "collapse_all"
        attrs["collapse_all"] = collapse_all_method

    _add_tree_model_methods(attrs, all_methods)


def _pad(args, n):
    """Pad a call's positional args out to `n` with None, so a partially
    specified call still lands in the right state slots."""
    args = list(args)
    while len(args) < n:
        args.append(None)
    return tuple(args)


def _style_path(path):
    """Hashable form of a path, for use as a style-map key."""
    return tuple(path) if isinstance(path, list) else path


def _model_rows(widget):
    """The flat row model in _state, whichever bulk setter filled it."""
    for key in ("rows", "data"):
        rows = widget._state.get(key)
        if isinstance(rows, list):
            return rows
    return None


def _drop_row_styles(widget):
    """The JS clear() that precedes a bulk load empties the per-cell and
    per-row style maps but keeps the column / table layers."""
    widget._state.pop("_cell_styles", None)
    widget._state.pop("_row_styles", None)


def _add_tree_model_methods(attrs, all_methods):
    """Override the tree/table mutators so they maintain the Python-side
    model (see :mod:`pgwidgets.tree_model`).

    Python is the source of truth: the browser can be rebuilt at any time
    from ``_state``, so every mutation has to be reflected there or it is
    lost on the next reconnect.  The bulk setters additionally deep-copy,
    so a caller that keeps editing the structure it passed in cannot
    corrupt the model behind our back.
    """
    # --- bulk setters: store a private copy, reset row-level styles ---
    for name, state_key in (("set_tree", "tree"), ("set_data", "data"),
                            ("set_rows", "rows")):
        if name not in all_methods:
            continue

        def make_bulk(mn, key, pn):
            def method(self, *args, **kwargs):
                args = _resolve_kwargs(mn, pn, args, kwargs)
                self._state[key] = tree_model.copy_tree(
                    args[0] if args else None)
                _drop_row_styles(self)
                return self._call(mn, *args)
            method.__name__ = mn
            return method
        attrs[name] = make_bulk(name, state_key, all_methods[name])

    # --- per-cell writes fold into the model ---
    if "set_cell" in all_methods:
        param_names = all_methods["set_cell"]

        def set_cell_method(self, *args, **kwargs):
            args = _resolve_kwargs("set_cell", param_names, args, kwargs)
            if len(args) >= 3:
                where, col, value = args[0], args[1], args[2]
                tree = self._state.get("tree")
                if isinstance(tree, dict):
                    tree_model.set_cell(tree, where, col, value)
                else:
                    rows = _model_rows(self)
                    if rows is not None:
                        tree_model.row_set_cell(
                            rows, self._state.get("columns"),
                            where, col, value)
            return self._call("set_cell", *args)
        set_cell_method.__name__ = "set_cell"
        attrs["set_cell"] = set_cell_method

    # --- structural tree edits ---
    if "add_item" in all_methods:
        param_names = all_methods["add_item"]

        def add_item_method(self, *args, **kwargs):
            args = _resolve_kwargs("add_item", param_names, args, kwargs)
            tree = self._state.get("tree")
            if isinstance(tree, dict) and len(args) >= 3:
                tree_model.add_item(tree, args[0], args[1], args[2])
            return self._call("add_item", *args)
        add_item_method.__name__ = "add_item"
        attrs["add_item"] = add_item_method

    if "remove_item" in all_methods:
        param_names = all_methods["remove_item"]

        def remove_item_method(self, *args, **kwargs):
            args = _resolve_kwargs("remove_item", param_names, args, kwargs)
            tree = self._state.get("tree")
            if isinstance(tree, dict) and args:
                tree_model.remove_item(tree, args[0])
            return self._call("remove_item", *args)
        remove_item_method.__name__ = "remove_item"
        attrs["remove_item"] = remove_item_method

    if "remove_items" in all_methods:
        param_names = all_methods["remove_items"]

        def remove_items_method(self, *args, **kwargs):
            args = _resolve_kwargs("remove_items", param_names, args, kwargs)
            tree = self._state.get("tree")
            if isinstance(tree, dict) and args:
                tree_model.remove_items(tree, args[0])
            return self._call("remove_items", *args)
        remove_items_method.__name__ = "remove_items"
        attrs["remove_items"] = remove_items_method

    if "add_tree" in all_methods:
        param_names = all_methods["add_tree"]

        def add_tree_method(self, *args, **kwargs):
            args = _resolve_kwargs("add_tree", param_names, args, kwargs)
            args = _pad(args, 2)
            tree = self._state.get("tree")
            if isinstance(tree, dict):
                tree_model.merge_tree(tree, args[0], args[1])
            elif isinstance(args[0], dict) and args[1] in (None, [], ()):
                # merging into an empty widget: the merge *is* the tree
                self._state["tree"] = tree_model.copy_tree(args[0])
            return self._call("add_tree", *args)
        add_tree_method.__name__ = "add_tree"
        attrs["add_tree"] = add_tree_method

    if "delete_tree" in all_methods:
        param_names = all_methods["delete_tree"]

        def delete_tree_method(self, *args, **kwargs):
            args = _resolve_kwargs("delete_tree", param_names, args, kwargs)
            args = _pad(args, 2)
            tree = self._state.get("tree")
            prune = True if args[1] is None else bool(args[1])
            if isinstance(tree, dict):
                tree_model.delete_tree(tree, args[0], prune)
            return self._call("delete_tree", *args)
        delete_tree_method.__name__ = "delete_tree"
        attrs["delete_tree"] = delete_tree_method

    if "update_tree" in all_methods:
        param_names = all_methods["update_tree"]

        def update_tree_method(self, *args, **kwargs):
            """Bring the tree to `tree`, sending only what changed.

            The browser's own ``update_tree`` is a full replacement (it
            rebuilds every row, dropping expansion state, cell styles and
            any open editor).  Because the model here is authoritative we
            can diff against it instead and send just the deltas.  A diff
            broader than a wholesale replacement falls back to
            ``set_tree``.
            """
            args = _resolve_kwargs("update_tree", param_names, args, kwargs)
            new_tree = args[0] if args else {}
            old_tree = self._state.get("tree")

            if not isinstance(old_tree, dict) or not isinstance(new_tree,
                                                                dict):
                self._state["tree"] = tree_model.copy_tree(new_tree)
                _drop_row_styles(self)
                return self._call("set_tree", new_tree)

            ops = tree_model.diff_tree(old_tree, new_tree)
            self._state["tree"] = tree_model.copy_tree(new_tree)
            if ops is None:
                # wholesale replacement -- the browser clears, so the
                # row-level style layers go with it
                _drop_row_styles(self)
                return self._call("set_tree", new_tree)
            result = None
            for op in ops:
                result = self._call(op[0], *op[1:])
            return result
        update_tree_method.__name__ = "update_tree"
        attrs["update_tree"] = update_tree_method

    # --- incremental flat-data update ---
    #
    # The browser diffs these against what it is showing, so the whole
    # array goes over the wire but only the rows that differ are
    # touched (selection, colours and scroll position survive).  The
    # model still has to record the new contents for reconnection.
    for name, default_key in (("update_data", "data"),
                              ("update_rows", "rows")):
        if name not in all_methods:
            continue

        def make_update_rows(mn, dk, pn):
            def method(self, *args, **kwargs):
                args = _resolve_kwargs(mn, pn, args, kwargs)
                key = dk
                for candidate in ("rows", "data"):
                    if isinstance(self._state.get(candidate), list):
                        key = candidate      # keep filling whichever
                        break                # bulk setter was used
                self._state[key] = tree_model.copy_tree(
                    args[0] if args else None)
                return self._call(mn, *args)
            method.__name__ = mn
            return method
        attrs[name] = make_update_rows(name, default_key, all_methods[name])

    # --- flat row edits ---
    for name, fn in (("insert_row", tree_model.insert_row),
                     ("append_row", tree_model.append_row),
                     ("delete_row", tree_model.delete_row)):
        if name not in all_methods:
            continue

        def make_row_op(mn, func, pn):
            def method(self, *args, **kwargs):
                args = _resolve_kwargs(mn, pn, args, kwargs)
                rows = _model_rows(self)
                if rows is not None:
                    if mn == "append_row":
                        func(rows, args[0] if args else None)
                    elif mn == "delete_row":
                        func(rows, args[0] if args else None)
                    else:
                        args2 = _pad(args, 2)
                        func(rows, args2[0], args2[1])
                return self._call(mn, *args)
            method.__name__ = mn
            return method
        attrs[name] = make_row_op(name, fn, all_methods[name])

    # --- column edits ---
    if "insert_column" in all_methods:
        param_names = all_methods["insert_column"]
        # TreeView is insert_column(column, before); TableView is
        # insert_column(index, column) -- tell them apart by the defn
        by_key = param_names and param_names[0] == "column"

        def insert_column_method(self, *args, **kwargs):
            args = _resolve_kwargs("insert_column", param_names,
                                   args, kwargs)
            args = _pad(args, 2)
            columns = self._state.get("columns")
            if isinstance(columns, list):
                if by_key:
                    tree_model.insert_column(columns, args[0],
                                             before=args[1])
                else:
                    tree_model.insert_column(columns, args[1],
                                             index=args[0])
            return self._call("insert_column", *args)
        insert_column_method.__name__ = "insert_column"
        attrs["insert_column"] = insert_column_method

    if "append_column" in all_methods:
        param_names = all_methods["append_column"]

        def append_column_method(self, *args, **kwargs):
            args = _resolve_kwargs("append_column", param_names,
                                   args, kwargs)
            columns = self._state.get("columns")
            if isinstance(columns, list) and args:
                tree_model.append_column(columns, args[0])
            return self._call("append_column", *args)
        append_column_method.__name__ = "append_column"
        attrs["append_column"] = append_column_method

    if "delete_column" in all_methods:
        param_names = all_methods["delete_column"]

        def delete_column_method(self, *args, **kwargs):
            args = _resolve_kwargs("delete_column", param_names,
                                   args, kwargs)
            columns = self._state.get("columns")
            if isinstance(columns, list) and args:
                # TreeView deletes by column key, TableView by index;
                # tree_model.delete_column accepts either
                tree_model.delete_column(columns, args[0])
            return self._call("delete_column", *args)
        delete_column_method.__name__ = "delete_column"
        attrs["delete_column"] = delete_column_method

    _add_colour_override_methods(attrs, all_methods)


def _record_style(widget, state_key, map_key, call_args, nkeys):
    """Record (or, when every colour channel is None, drop) one override.

    ``call_args`` is the equivalent single-call argument tuple, so the
    stored entry can be replayed by re-dispatch regardless of whether it
    arrived singly or as part of a batch.
    """
    if all(v is None for v in call_args[nkeys:]):
        widget._state.get(state_key, {}).pop(map_key, None)
    else:
        widget._state.setdefault(state_key, {})[map_key] = call_args


def _add_colour_override_methods(attrs, all_methods):
    """Accumulate the per-cell / row / column / table colour overrides.

    These have no bulk setter to fold into, so they are kept as maps in
    _state and replayed on top of the data during reconstruction.  An
    all-null call clears that layer, matching the JS.
    """
    # method, total args, state key, number of leading key args
    # (the remaining args are the fg / bg / bold channels)
    specs = [
        ("set_cell_color", 5, "_cell_styles", 2),
        ("set_row_color", 4, "_row_styles", 1),
        ("set_column_color", 4, "_column_styles", 1),
        ("set_table_color", 3, "_table_style", 0),
    ]
    for name, nargs, state_key, nkeys in specs:
        if name not in all_methods:
            continue

        def make_setter(mn, n, sk, nk, pn):
            def method(self, *args, **kwargs):
                args = _resolve_kwargs(mn, pn, args, kwargs)
                args = _pad(args, n)
                cleared = all(v is None for v in args[nk:])
                if nk == 0:                       # table-wide: one slot
                    if cleared:
                        self._state.pop(sk, None)
                    else:
                        self._state[sk] = tuple(args)
                else:
                    map_key = ((_style_path(args[0]), args[1]) if nk == 2
                               else _style_path(args[0]))
                    if cleared:
                        self._state.get(sk, {}).pop(map_key, None)
                    else:
                        # keep the whole call, so replaying is a
                        # straight re-dispatch
                        self._state.setdefault(sk, {})[map_key] = tuple(args)
                return self._call(mn, *args)
            method.__name__ = mn
            return method
        attrs[name] = make_setter(name, nargs, state_key, nkeys,
                                  all_methods[name])

    clears = [
        ("clear_cell_color", "_cell_styles",
         lambda a: (_style_path(a[0]), a[1])),
        ("clear_row_color", "_row_styles", lambda a: _style_path(a[0])),
        ("clear_column_color", "_column_styles", lambda a: a[0]),
    ]
    for name, state_key, keyfn in clears:
        if name not in all_methods:
            continue

        def make_clear_one(mn, sk, kf, pn):
            def method(self, *args, **kwargs):
                args = _resolve_kwargs(mn, pn, args, kwargs)
                args = _pad(args, 2)
                self._state.get(sk, {}).pop(kf(args), None)
                return self._call(mn, *args)
            method.__name__ = mn
            return method
        attrs[name] = make_clear_one(name, state_key, keyfn,
                                     all_methods[name])

    if "set_colors" in all_methods:
        param_names = all_methods["set_colors"]

        def set_colors_method(self, *args, **kwargs):
            """Apply many colour overrides in one call.

            Folds the batch into the same style maps the single-cell
            setters use, so the model stays accurate for reconnection
            while costing one round-trip and one browser re-render
            instead of one of each per cell.
            """
            args = _resolve_kwargs("set_colors", param_names, args, kwargs)
            spec = args[0] if args else None
            if isinstance(spec, dict):
                if spec.get("clear"):
                    for key in ("_cell_styles", "_row_styles",
                                "_column_styles", "_table_style"):
                        self._state.pop(key, None)
                for e in (spec.get("cells") or []):
                    _record_style(
                        self, "_cell_styles",
                        (_style_path(e.get("path")), e.get("col_key")),
                        (e.get("path"), e.get("col_key"), e.get("fg"),
                         e.get("bg"), e.get("bold")), 2)
                for e in (spec.get("rows") or []):
                    _record_style(
                        self, "_row_styles", _style_path(e.get("path")),
                        (e.get("path"), e.get("fg"), e.get("bg"),
                         e.get("bold")), 1)
                for e in (spec.get("columns") or []):
                    _record_style(
                        self, "_column_styles", e.get("col_key"),
                        (e.get("col_key"), e.get("fg"), e.get("bg"),
                         e.get("bold")), 1)
                if "table" in spec:
                    t = spec.get("table") or {}
                    channels = (t.get("fg"), t.get("bg"), t.get("bold"))
                    if all(v is None for v in channels):
                        self._state.pop("_table_style", None)
                    else:
                        self._state["_table_style"] = channels
            return self._call("set_colors", *args)
        set_colors_method.__name__ = "set_colors"
        attrs["set_colors"] = set_colors_method

    if "clear_all_colors" in all_methods:
        def clear_all_colors_method(self):
            for key in ("_cell_styles", "_row_styles", "_column_styles",
                        "_table_style"):
                self._state.pop(key, None)
            return self._call("clear_all_colors")
        clear_all_colors_method.__name__ = "clear_all_colors"
        attrs["clear_all_colors"] = clear_all_colors_method


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

    # Add error stubs for unsupported methods
    for (wc, mn), msg in UNSUPPORTED_METHODS.items():
        if wc == js_class:
            def _make_unsupported(name, message):
                def method(self, *args, **kwargs):
                    raise NotImplementedError(message)
                method.__name__ = name
                return method
            attrs[mn] = _make_unsupported(mn, msg)

    # Inject custom Python-side method implementations
    for (wc, mn), func in CUSTOM_METHODS.items():
        if wc == js_class:
            attrs[mn] = func

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
    body_prefix = "_pos = []\n    " if pos_names else ""
    exec_src = f"""
def __init__({_init_params(pos_names, opt_names)}):
    {body_prefix}{_init_body(pos_names, opt_names)}
"""
    exec(exec_src, ns)
    cls.__init__ = ns["__init__"]

    return cls


def _init_params(pos_names, opt_names):
    """Build the parameter string for the generated __init__.

    Options are exposed as positional-or-keyword (no ``*`` separator)
    so that single-option widgets like Frame accept ``Frame("Title")``
    in addition to ``Frame(title="Title")``, matching the pyodide
    bridge's behavior.  Each option still defaults to ``None`` so
    omitted ones don't override state from prior calls.
    """
    params = ["self", "session"]
    for name in pos_names:
        params.append(f"{name}=None")
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
        default = STATE_DEFAULTS.get(widget_name, {}).get(info)
        if default is None:
            default = STATE_KEY_DEFAULTS.get(info)
        attrs[method_name] = _make_getter(method_name, info, default)

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
    # TextSource is hand-written (Python-authoritative local text model)
    # rather than generated -- see pgwidgets.sync.text_source.  Deferred
    # import avoids a circular import at module load.
    from pgwidgets.sync.text_source import TextSource as _TextSource
    classes['TextSource'] = _TextSource
    return classes
