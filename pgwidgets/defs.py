"""
Widget class definitions used to generate Python wrapper classes.

Each entry maps a JS class name to its constructor signature and
public methods.  The 'args' list gives positional constructor args;
'options' lists keyword args that go into the options object.
'methods' maps method names to their parameter names (excluding self/widget).
'callbacks' lists the callback actions the widget supports.
"""

# Common methods inherited from Widget base class
WIDGET_METHODS = {
    "get_element": [],
    "set_border_width": ["width"],
    "set_border_color": ["color"],
    "resize": ["width", "height"],
    "get_size": [],
    "set_padding": ["padding"],
    "set_font": ["font", "size", "weight", "style"],
    "set_enabled": ["tf"],
    "get_enabled": [],
    "show": [],
    "hide": [],
    "is_visible": [],
}

# Common methods from ContainerWidget
CONTAINER_METHODS = {
    **WIDGET_METHODS,
    "get_children": [],
}

# ---- Widget Definitions ----

WIDGETS = {

    # -- Layout containers --

    "VBox": {
        "base": "container",
        "args": [],
        "options": [],
        "methods": {
            "add_widget": ["child", "stretch"],
            "set_spacing": ["gap"],
        },
        "callbacks": [],
    },

    "HBox": {
        "base": "container",
        "args": [],
        "options": [],
        "methods": {
            "add_widget": ["child", "stretch"],
            "set_spacing": ["gap"],
        },
        "callbacks": [],
    },

    "ButtonBox": {
        "base": "container",
        "args": [],
        "options": ["orientation"],
        "methods": {
            "add_widget": ["child", "stretch"],
            "set_spacing": ["gap"],
        },
        "callbacks": [],
    },

    "GridBox": {
        "base": "container",
        "args": [],
        "options": ["rows", "columns"],
        "methods": {
            "add_widget": ["child", "row", "col"],
            "set_row_spacing": ["px"],
            "set_column_spacing": ["px"],
            "set_spacing": ["px"],
            "get_row_column_count": [],
            "get_widget_at_cell": ["row", "col"],
            "insert_row": ["index", "widgets"],
            "append_row": ["widgets"],
            "delete_row": ["index"],
            "insert_column": ["index", "widgets"],
            "append_column": ["widgets"],
            "delete_column": ["index"],
        },
        "callbacks": [],
    },

    "Splitter": {
        "base": "container",
        "args": [],
        "options": ["orientation"],
        "methods": {
            "add_widget": ["child"],
            "set_sizes": ["sizes"],
            "get_sizes": [],
        },
        "callbacks": [],
    },

    "Frame": {
        "base": "widget",
        "args": [],
        "options": ["title"],
        "methods": {
            "set_widget": ["child"],
            "set_title": ["text"],
        },
        "callbacks": [],
    },

    "Expander": {
        "base": "widget",
        "args": [],
        "options": ["title", "collapsible", "shadow"],
        "methods": {
            "set_widget": ["child"],
            "toggleContent": [],
        },
        "callbacks": [],
    },

    "ScrollArea": {
        "base": "widget",
        "args": [],
        "options": ["hscrollbar", "vscrollbar"],
        "methods": {
            "set_widget": ["child"],
        },
        "callbacks": [],
    },

    "TabWidget": {
        "base": "container",
        "args": [],
        "options": ["closable", "reorderable", "tab_position"],
        "methods": {
            "add_widget": ["child", "options"],
            "show_widget": ["child"],
            "close_widget": ["child"],
            "set_index": ["index"],
            "get_index": [],
            "get_tab_id": ["child"],
            "get_child": ["tab_id"],
            "index_of": ["child"],
            "highlight_tab": ["child", "bgcolor"],
            "set_tab_position": ["tabpos"],
        },
        "callbacks": ["page-switch", "page-close"],
    },

    "StackWidget": {
        "base": "container",
        "args": [],
        "options": [],
        "methods": {
            "add_widget": ["child", "options"],
            "show_widget": ["child"],
            "set_index": ["index"],
            "get_index": [],
        },
        "callbacks": ["page-switch"],
    },

    "MDIWidget": {
        "base": "container",
        "args": [],
        "options": [],
        "methods": {
            "add_widget": ["child", "options"],
            "cascade_windows": [],
            "tile_windows": [],
            "get_subwin": ["child"],
            "close_child": ["child"],
            "set_resistance": ["value"],
        },
        "callbacks": ["page-switch", "page-close"],
    },

    # -- Top-level windows --

    "TopLevel": {
        "base": "widget",
        "args": [],
        "options": ["resizable", "title", "moveable"],
        "methods": {
            "set_position": ["x", "y"],
            "set_widget": ["child"],
            "set_title": ["title"],
            "set_moveable": ["tf"],
        },
        "callbacks": [],
    },

    "Page": {
        "base": "widget",
        "args": [],
        "options": [],
        "methods": {
            "set_widget": ["child"],
        },
        "callbacks": [],
    },

    "Dialog": {
        "base": "widget",
        "args": ["title", "buttons"],
        "options": ["autoclose", "resizable", "moveable", "modal"],
        "methods": {
            "get_content_area": [],
        },
        "callbacks": ["activated"],
    },

    "ColorDialog": {
        "base": "widget",
        "args": [],
        "options": ["color", "title", "modal", "moveable"],
        "methods": {
            "get_color": [],
            "set_color": ["hex_string"],
        },
        "callbacks": ["activated", "pick"],
    },

    # -- Buttons --

    "Button": {
        "base": "widget",
        "args": ["text"],
        "options": [],
        "methods": {
            "set_text": ["text"],
            "set_icon": ["url", "size"],
            "set_color": ["bg", "fg"],
        },
        "callbacks": ["activated"],
    },

    "CheckBox": {
        "base": "widget",
        "args": ["text"],
        "options": [],
        "methods": {
            "set_state": ["tf"],
            "get_state": [],
        },
        "callbacks": ["activated"],
    },

    "RadioButton": {
        "base": "widget",
        "args": ["text"],
        "options": ["group"],
        "methods": {
            "set_text": ["text"],
            "set_state": ["value"],
            "get_state": [],
        },
        "callbacks": ["activated"],
    },

    "ToggleButton": {
        "base": "widget",
        "args": ["text"],
        "options": ["group"],
        "methods": {
            "set_text": ["text"],
            "set_state": ["value"],
            "get_state": [],
        },
        "callbacks": ["activated"],
    },

    # -- Text --

    "Label": {
        "base": "widget",
        "args": ["text"],
        "options": ["halign"],
        "methods": {
            "set_text": ["text"],
            "get_text": [],
            "set_color": ["bg", "fg"],
            "set_halign": ["align"],
        },
        "callbacks": [],
    },

    "TextEntry": {
        "base": "widget",
        "args": [],
        "options": ["text", "editable", "linehistory", "password"],
        "methods": {
            "set_text": ["text"],
            "get_text": [],
            "clear": [],
            "set_length": ["numchars"],
        },
        "callbacks": ["activated"],
    },

    "TextEntrySet": {
        "base": "widget",
        "args": [],
        "options": ["text", "value", "editable", "linehistory"],
        "methods": {
            "set_button_text": ["text"],
            "set_text": ["text"],
            "get_text": [],
            "clear": [],
            "set_length": ["numchars"],
        },
        "callbacks": ["activated"],
    },

    "TextArea": {
        "base": "widget",
        "args": ["text"],
        "options": ["wrap", "editable"],
        "methods": {
            "set_text": ["text"],
            "get_text": [],
            "append_text": ["text"],
            "clear": [],
            "set_editable": ["tf"],
            "set_wrap": ["tf"],
            "set_limit": ["numlines"],
        },
        "callbacks": [],
    },

    # -- Value widgets --

    "ComboBox": {
        "base": "widget",
        "args": [],
        "options": ["editable", "dropdown_limit"],
        "methods": {
            "append_text": ["text"],
            "insert_alpha": ["text"],
            "delete_alpha": ["text"],
            "set_text": ["text"],
            "get_text": [],
            "set_index": ["idx"],
            "get_index": [],
            "get_alpha": ["idx"],
            "clear": [],
            "set_length": ["numchars"],
        },
        "callbacks": ["activated"],
    },

    "SpinBox": {
        "base": "widget",
        "args": [],
        "options": ["dtype", "min", "max", "step", "value"],
        "methods": {
            "set_value": ["val"],
            "get_value": [],
            "set_limits": ["minval", "maxval", "incrval"],
        },
        "callbacks": ["activated"],
    },

    "Slider": {
        "base": "widget",
        "args": [],
        "options": ["orientation", "track", "dtype", "min", "max",
                    "step", "value", "show_value"],
        "methods": {
            "set_value": ["num"],
            "get_value": [],
            "set_limits": ["minval", "maxval", "incrval"],
            "set_tracking": ["track"],
        },
        "callbacks": ["activated"],
    },

    "Dial": {
        "base": "widget",
        "args": [],
        "options": ["track", "dtype", "min", "max", "step", "value"],
        "methods": {
            "set_value": ["num"],
            "get_value": [],
            "set_limits": ["minval", "maxval", "incrval"],
            "set_tracking": ["track"],
        },
        "callbacks": ["activated"],
    },

    "ScrollBar": {
        "base": "widget",
        "args": [],
        "options": ["orientation", "thickness"],
        "methods": {
            "set_scroll_percent": ["pct"],
            "get_scroll_percent": [],
            "set_thumb_width": ["pct"],
        },
        "callbacks": ["activated"],
    },

    "ProgressBar": {
        "base": "widget",
        "args": [],
        "options": [],
        "methods": {
            "set_value": ["value"],
            "get_value": [],
        },
        "callbacks": [],
    },

    # -- Display --

    "Image": {
        "base": "widget",
        "args": [],
        "options": ["url"],
        "methods": {
            "set_image": ["url"],
        },
        "callbacks": [],
    },

    "Canvas": {
        "base": "widget",
        "args": [],
        "options": [],
        "methods": {
            "initialize_events": [],
        },
        "callbacks": ["pointer-down", "pointer-up", "pointer-move",
                      "pointer-over", "pointer-out", "click", "dblclick",
                      "wheel", "keydown", "keyup", "keypress", "focus",
                      "focusout", "drop", "dragover", "contextmenu",
                      "activated"],
    },

    # -- Menus & Toolbars --

    "MenuBar": {
        "base": "widget",
        "args": [],
        "options": [],
        "methods": {
            "add_menu": ["menu", "name"],
            "add_name": ["name"],
            "get_menu": ["name"],
        },
        "callbacks": [],
    },

    "Menu": {
        "base": "widget",
        "args": [],
        "options": [],
        "methods": {
            "add_widget": ["child"],
            "add_name": ["name", "checkable"],
            "add_menu": ["name", "menu"],
            "add_separator": [],
            "popup": [],
        },
        "callbacks": [],
    },

    "MenuAction": {
        "base": "widget",
        "args": [],
        "options": ["text", "icon_url", "iconsize", "checkable", "name"],
        "methods": {
            "set_text": ["text"],
            "get_text": [],
            "set_icon": ["url", "iconsize"],
            "set_checked": ["checked"],
            "get_checked": [],
        },
        "callbacks": ["activated"],
    },

    "ToolBar": {
        "base": "widget",
        "args": [],
        "options": ["orientation"],
        "methods": {
            "add_widget": ["child"],
            "add_separator": [],
            "add_spacer": [],
            "add_action": ["options"],
        },
        "callbacks": [],
    },

    "ToolBarAction": {
        "base": "widget",
        "args": [],
        "options": ["text", "icon_url", "iconsize", "toggle", "group"],
        "methods": {
            "set_text": ["text"],
            "get_text": [],
            "set_icon": ["url", "iconsize"],
            "set_state": ["value"],
            "get_state": [],
        },
        "callbacks": ["activated"],
    },
}
