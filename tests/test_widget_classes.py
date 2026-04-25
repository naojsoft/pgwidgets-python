"""
Tests for widget class generation.

Verifies that build_widget_class produces classes with the correct
methods for each widget definition.
"""

from pgwidgets.defs import (
    WIDGETS, CALLBACK_METHODS, WIDGET_METHODS, CONTAINER_METHODS,
)
from pgwidgets.sync.widget import build_widget_class, build_all_widget_classes


def test_build_all_returns_all_widgets():
    """build_all_widget_classes should return a class for every entry
    in WIDGETS."""
    classes = build_all_widget_classes()
    assert set(classes.keys()) == set(WIDGETS.keys())


def test_widget_classes_have_base_methods():
    """Every generated widget class should have the methods from its
    base type."""
    classes = build_all_widget_classes()
    for name, cls in classes.items():
        defn = WIDGETS[name]
        base = defn["base"]
        if base == "container":
            base_methods = CONTAINER_METHODS
        elif base == "callback":
            base_methods = CALLBACK_METHODS
        else:
            base_methods = WIDGET_METHODS

        for mname in base_methods:
            assert hasattr(cls, mname), (
                f"{name} missing base method {mname}")


def test_widget_classes_have_own_methods():
    """Every generated widget class should have its per-widget methods."""
    classes = build_all_widget_classes()
    for name, cls in classes.items():
        defn = WIDGETS[name]
        for mname in defn["methods"]:
            assert hasattr(cls, mname), (
                f"{name} missing method {mname}")


def test_widget_classes_have_on_and_add_callback():
    """Every generated widget class should inherit on() and
    add_callback() from the base Widget."""
    classes = build_all_widget_classes()
    for name, cls in classes.items():
        assert hasattr(cls, "on"), f"{name} missing on()"
        assert hasattr(cls, "add_callback"), (
            f"{name} missing add_callback()")


def test_widget_classes_have_destroy():
    """Every generated widget class should have destroy()."""
    classes = build_all_widget_classes()
    for name, cls in classes.items():
        assert hasattr(cls, "destroy"), f"{name} missing destroy()"


def test_callback_base_has_fewer_methods():
    """Widgets with base='callback' should NOT have DOM methods like
    resize, show, hide."""
    classes = build_all_widget_classes()
    dom_methods = {"resize", "show", "hide", "set_border_width",
                   "set_font", "set_padding",
                   "set_min_size", "set_max_size"}
    for name, cls in classes.items():
        defn = WIDGETS[name]
        if defn["base"] == "callback":
            for mname in dom_methods:
                # Should not have these unless explicitly defined
                if mname not in defn["methods"]:
                    assert not hasattr(cls, mname), (
                        f"callback-based {name} should not have "
                        f"DOM method {mname}")


def test_generated_method_names_match():
    """The __name__ of generated methods should match the method name."""
    cls = build_widget_class("Label", WIDGETS["Label"])
    assert cls.set_text.__name__ == "set_text"
    assert cls.get_text.__name__ == "get_text"


def test_generated_method_has_docstring():
    """Generated methods should have a docstring with param info."""
    cls = build_widget_class("Label", WIDGETS["Label"])
    assert cls.set_text.__doc__ is not None
    assert "text" in cls.set_text.__doc__


def test_class_stores_metadata():
    """Generated classes should store the JS class name and definition."""
    cls = build_widget_class("Button", WIDGETS["Button"])
    assert cls._js_class_name == "Button"
    assert cls._defn is WIDGETS["Button"]
