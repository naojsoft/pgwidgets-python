"""
Method classification for stateful widget generation.

Categorizes widget methods so the class generator knows which methods
track state locally, which manage the widget tree, and which are
fire-and-forget actions.

Categories:
    SETTER  - stores value in _state, sends to browser
    GETTER  - returns from _state (no round-trip)
    CHILD   - manages parent-child relationships
    ACTION  - fire-and-forget, no state tracking
    JS_ONLY - browser-only, not meaningful for reconstruction
"""

SETTER = "setter"
GETTER = "getter"
CHILD = "child"
ACTION = "action"
JS_ONLY = "js_only"

# -- Explicit overrides (take precedence over conventions) --

# Methods that manage the widget tree.
# Values: "multi" = appends to children list, "single" = replaces child
CHILD_METHODS = {
    "add_widget": "multi",
    "add_button": "multi",
    "insert_widget": "multi",
    "set_widget": "single",
    "add_menu": "multi",
    "add_name": "multi",
    "add_action": "multi",
    "remove": "remove",
    "remove_widget": "remove",
    "remove_all": "remove_all",
}

# Methods that only make sense in the browser
JS_ONLY_METHODS = {
    "get_element", "get_draw_context", "get_video_element",
    "get_content_element", "get_position",
    # Timer runtime queries
    "is_set", "elapsed_time", "time_left",
    # TextSource runtime queries
    "can_undo", "can_redo", "get_cursor", "get_selection",
    "get_tags_at",
    # VideoWidget runtime state
    "get_duration", "get_paused",
    # TreeView/TableView runtime queries
    "get_selected", "get_expanded", "get_collapsed",
    "get_column_count", "get_row_count",
    "get_widget_at_cell", "get_row_column_count",
    # Dialog
    "get_content_area",
    # ComboBox
    "get_alpha",
    # Container
    "num_children",
    # TabWidget lookups
    "get_tab_id", "get_child", "index_of",
    # MDIWidget
    "get_subwin", "get_subwindows", "get_configuration",
    "get_child_size", "get_child_position",
    # Button icon (set_icon is an action, so get_icon must round-trip)
    "get_icon",
}

# Action methods: fire-and-forget, no state tracking
ACTION_METHODS = {
    "set_focus",
    # Scrolling
    "scroll_to_top", "scroll_to_bottom", "scroll_to",
    "scroll_to_cursor", "scroll_to_path", "scroll_to_end",
    # Video/media
    "play", "pause", "stop", "fullscreen",
    # FileDialog
    "open", "save",
    # Menu
    "popup", "add_separator", "add_spacer",
    # Tree/table manipulation
    "expand_all", "collapse_all", "expand_item", "collapse_item",
    "sort_by_column", "set_optimal_column_widths",
    "select_path", "select_paths", "select_all",
    # TextSource editing
    "insert_text", "delete_range", "create_tag", "remove_tag_def",
    "apply_tag", "remove_tag", "create_ref", "remove_ref",
    "set_cursor", "set_selection",
    "undo", "redo", "find", "find_all", "replace",
    # Canvas
    "update", "draw_image",
    # Layout actions
    "cascade_windows", "tile_windows",
    "toggleContent",
    "raise_", "lower",
    # Timer
    "start", "cancel", "set", "cond_set",
    # Table/Tree row-level modifications (tracked via bulk set_data)
    "add_item", "remove_item", "update_tree", "remove_items",
    "insert_row", "append_row", "delete_row",
    "insert_column", "append_column", "delete_column",
    "set_cell",
    # ComboBox item manipulation (tracked via bulk state)
    "append_text", "insert_alpha", "delete_alpha",
    # TabWidget/MDI child management
    "show_widget", "close_widget", "close_child",
    "move", "move_child", "resize_child",
    "highlight_tab",
    # Splitter per-child
    "set_minimum_size",
    # TreeView per-column
    "set_column_width", "set_column_editable",
    # TextSource per-line
    "set_icon",
}

# Setter methods that DON'T follow the set_* naming convention.
# Maps method_name -> state_key
SPECIAL_SETTERS = {
    "resize": "size",
}

# Setter methods with fixed values (no parameters).
# Maps method_name -> (state_key, value)
FIXED_SETTERS = {
    "show": ("visible", True),
    "hide": ("visible", False),
}

# Getter methods that DON'T follow the get_* naming convention.
# Maps method_name -> state_key
SPECIAL_GETTERS = {
    "is_visible": "visible",
    "get_size": "size",
}

# Callbacks whose args should automatically update widget state on
# the Python side.  Maps callback action -> state_key.
# When the browser fires one of these, the args are stored as a
# tuple in widget._state[state_key] so reconstruction can replay.
STATE_SYNC_CALLBACKS = {
    "move": "position",
    "resize": "size",
}

# Auto-sync callbacks that should only be listened for on widgets
# whose definition includes certain options.  Maps callback action
# to the required option name.
STATE_SYNC_REQUIRES_OPTION = {
    "resize": "resizable",
}

# Per-widget-class state sync from browser callbacks.
# When the browser fires a callback listed here, args are stored in
# widget._state so reconstruction can replay the current state.
#
# Value is either a single state_key (syncs args[0]) or a list of
# (arg_index, state_key) tuples for multi-arg callbacks.
#
# Maps widget_class -> {callback_action: state_key | [(idx, key), ...]}
WIDGET_CALLBACK_SYNC = {
    "ScrollBar": {"activated": "scroll_percent"},
    "Slider": {"activated": "value"},
    "SpinBox": {"activated": "value"},
    "Dial": {"activated": "value"},
    "CheckBox": {"activated": "state"},
    "RadioButton": {"activated": "state"},
    "ToggleButton": {"activated": "state"},
    "TextEntry": {"activated": "text", "modified": "text"},
    "TextEntrySet": {"activated": "text", "modified": "text"},
    "TextArea": {"activated": "text", "modified": "text"},
    "ComboBox": {"activated": [(0, "index"), (1, "text")],
                 "modified": "text"},
    "AbstractScrollArea": {"scrolled": ("scroll_percent",)},
    "ScrollArea": {"scrolled": ("scroll_percent",)},
    "Splitter": {"sizing": "sizes"},
    "Expander": {"toggled": "collapsed"},
    "ToolBarAction": {"activated": "state"},
    "TabWidget": {"page-switch": [(1, "index")]},
    "StackWidget": {"page-switch": [(1, "index")]},
}

# Container callbacks that manage the child list automatically.
# When the browser fires one of these, the Python side removes the
# child from _children so it won't be reconstructed.
# Maps callback action -> argument interpretation.
CHILD_CLOSE_CALLBACKS = {
    "page-close",   # MDIWidget: arg is the content child widget
}

# Methods that create content from non-Widget args and must be
# replayed during reconstruction.  These are typically factory methods
# (add_action, add_name) that return auto-wrapped JS widgets, plus
# layout modifiers (add_separator, add_spacer) whose order matters.
# Calls are recorded in widget._replay_calls as
# (method_name, args, returned_widget_or_None).
REPLAY_METHODS = {
    "add_name", "add_action", "add_menu", "add_separator", "add_spacer",
}

# Factory methods that create and return a new widget on the JS side.
# When called with no browser connected, a local proxy of the correct
# class is created so the caller can continue building the widget tree.
# Maps (parent_class, method_name) -> returned JS class name.
FACTORY_RETURN_TYPES = {
    ("MenuBar", "add_name"): "Menu",
    ("MenuBar", "add_menu"): "Menu",
    ("Menu", "add_name"): "MenuAction",
    ("Menu", "add_menu"): "Menu",
    ("ToolBar", "add_action"): "ToolBarAction",
}

# Methods that select a child and should track the index in _state.
# Maps method_name -> state_key.  When called with a Widget arg, the
# child's position in _children is stored as the index.
CHILD_SELECT_METHODS = {
    "show_widget": "index",
}

# State keys that must be replayed AFTER children are attached
# (e.g. Splitter.set_sizes needs panes to already exist).
POST_CHILDREN_STATE_KEYS = {"sizes", "index", "_collapsed_paths",
                            "_expanded_paths", "_sort", "scroll_position",
                            "scroll_percent"}

# Default state values applied when a widget is created without
# explicitly setting the key (e.g. TextEntry() with no text arg).
STATE_DEFAULTS = {
    "TextEntry": {"text": ""},
    "TextEntrySet": {"text": ""},
    "TextArea": {"text": ""},
    "TextSource": {"text": ""},
    "ComboBox": {"text": ""},
    "TabWidget": {"index": -1},
    "StackWidget": {"index": -1},
    "MDIWidget": {"index": -1},
}

# Cross-widget default values for state keys, used as a fallback when
# STATE_DEFAULTS has no per-widget entry.  Lets getters return a
# sensible value before any browser has reported state (e.g. before
# the widget has been laid out).
STATE_KEY_DEFAULTS = {
    "size": (0, 0),
    "position": (0, 0),
    "index": -1,
}

# Widgets with incrementally-built item lists.
# These action methods are wrapped to maintain _state["_items"].
# During reconstruction the items are replayed via the "append" method.
ITEM_LIST_CONFIG = {
    "ComboBox": {
        "key": "_items",
        "append": "append_text",     # method(text)
        "insert": "insert_alpha",    # method(text, index)
        "delete": "delete_alpha",    # method(index)
    },
}

# Widgets that track expand/collapse and sort state.
# These action methods are overridden to maintain _state keys that
# are replayed during reconstruction.
TREE_VIEW_WIDGETS = {"TreeView", "TableView"}

# clear() resets these state keys per widget type.
# If a widget is not listed, clear() is treated as a plain action.
CLEAR_RESETS = {
    "TextEntry": ["text"],
    "TextEntrySet": ["text"],
    "TextArea": ["text"],
    "TextSource": ["text"],
    "ComboBox": ["text", "index", "_items"],
    "TreeView": ["tree", "data", "columns", "_collapsed_paths", "_sort"],
    "TableView": ["rows", "data", "columns", "_collapsed_paths", "_sort"],
    "HtmlView": ["html"],
    "ExternalWidget": ["content"],
}


# Methods that are JS-only and should raise an error on the Python side
# with a helpful message.  Maps (widget_class, method_name) -> message.
UNSUPPORTED_METHODS = {
    ("Dialog", "get_content_area"):
        "get_content_area() is not supported on the Python side. "
        "Use add_widget(), insert_widget(), and set_spacing() directly "
        "on the Dialog instead.",
}


# Methods with custom Python-side implementations that bypass the
# auto-generated browser round-trip.  Maps (widget_class, method_name)
# to a function(self, ...) that is used directly as the method body.
def _index_to_widget(self, index):
    if index < 0 or index >= len(self._children):
        return None
    return self._children[index][0]

def _index_of(self, child):
    for i, entry in enumerate(self._children):
        if entry[0] is child:
            return i
    return -1

def _dialog_popup(self, x=None, y=None):
    self._state["visible"] = True
    if x is not None and y is not None:
        self._state["position"] = (x, y)
    return self._call("popup", x, y)

def _get_menu(self, name):
    for entry in self._replay_calls:
        if entry[0] == "add_menu" and entry[1] and entry[1][0] == name:
            return entry[2]
    return None

def _menuaction_set_state(self, tf):
    """Alias for MenuAction.set_checked — keeps a single state key."""
    return self.set_checked(tf)

def _menuaction_get_state(self):
    """Alias for MenuAction.get_checked — keeps a single state key."""
    return self.get_checked()

CUSTOM_METHODS = {
    ("TabWidget", "index_to_widget"): _index_to_widget,
    ("TabWidget", "index_of"): _index_of,
    ("StackWidget", "index_to_widget"): _index_to_widget,
    ("StackWidget", "index_of"): _index_of,
    ("MDIWidget", "index_to_widget"): _index_to_widget,
    ("MDIWidget", "index_of"): _index_of,
    ("Menu", "get_menu"): _get_menu,
    ("MenuBar", "get_menu"): _get_menu,
    ("Dialog", "popup"): _dialog_popup,
    ("MenuAction", "set_state"): _menuaction_set_state,
    ("MenuAction", "get_state"): _menuaction_get_state,
}


def _state_key_for_setter(method_name):
    """Derive the state key from a set_* method name."""
    if method_name in SPECIAL_SETTERS:
        return SPECIAL_SETTERS[method_name]
    if method_name in FIXED_SETTERS:
        return FIXED_SETTERS[method_name][0]
    if method_name.startswith("set_"):
        return method_name[4:]
    return None


def _state_key_for_getter(method_name):
    """Derive the state key from a get_* or special getter."""
    if method_name in SPECIAL_GETTERS:
        return SPECIAL_GETTERS[method_name]
    if method_name.startswith("get_"):
        return method_name[4:]
    return None


def classify_method(method_name, param_names, all_methods):
    """Classify a widget method.

    Returns (category, state_key) where state_key is the key into
    _state for setters/getters, or None for other categories.
    """
    # Explicit overrides first
    if method_name in CHILD_METHODS:
        return CHILD, CHILD_METHODS[method_name]
    if method_name in JS_ONLY_METHODS:
        return JS_ONLY, None
    if method_name in ACTION_METHODS:
        return ACTION, None

    # Fixed-value setters (show, hide)
    if method_name in FIXED_SETTERS:
        key, _ = FIXED_SETTERS[method_name]
        return SETTER, key

    # Special setters (resize)
    if method_name in SPECIAL_SETTERS:
        return SETTER, SPECIAL_SETTERS[method_name]

    # Special getters (is_visible)
    if method_name in SPECIAL_GETTERS:
        return GETTER, SPECIAL_GETTERS[method_name]

    # Convention: set_X with params -> setter
    if method_name.startswith("set_") and param_names:
        return SETTER, method_name[4:]

    # Convention: get_X with no params and matching set_X -> getter
    if method_name.startswith("get_") and not param_names:
        key = method_name[4:]
        setter = f"set_{key}"
        if setter in all_methods:
            return GETTER, key
        # No matching setter — treat as JS-only query
        return JS_ONLY, None

    # clear() is special — handled by the generator using CLEAR_RESETS
    if method_name == "clear":
        return ACTION, None

    # Default: action
    return ACTION, None
