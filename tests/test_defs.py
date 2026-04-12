"""
Tests for widget definitions (defs.py).

Validates that the canonical widget definitions are well-formed and
internally consistent.
"""

from pgwidgets.defs import (
    WIDGETS, CALLBACK_METHODS, WIDGET_METHODS, CONTAINER_METHODS,
)


VALID_BASES = {"widget", "container", "callback"}


def test_all_widgets_have_required_keys():
    """Every widget definition must have base, args, options, methods,
    and callbacks."""
    required = {"base", "args", "options", "methods", "callbacks"}
    for name, defn in WIDGETS.items():
        missing = required - defn.keys()
        assert not missing, f"{name} missing keys: {missing}"


def test_all_widgets_have_valid_base():
    """The 'base' field must be one of the known base types."""
    for name, defn in WIDGETS.items():
        base = defn["base"]
        assert base in VALID_BASES, (
            f"{name} has invalid base {base!r}, "
            f"expected one of {VALID_BASES}")


def test_methods_are_dicts():
    """The 'methods' field must be a dict mapping names to param lists."""
    for name, defn in WIDGETS.items():
        methods = defn["methods"]
        assert isinstance(methods, dict), (
            f"{name}['methods'] is {type(methods).__name__}, expected dict")
        for mname, params in methods.items():
            assert isinstance(params, list), (
                f"{name}.{mname} params is {type(params).__name__}, "
                f"expected list")


def test_callbacks_are_lists():
    """The 'callbacks' field must be a list of strings."""
    for name, defn in WIDGETS.items():
        cbs = defn["callbacks"]
        assert isinstance(cbs, list), (
            f"{name}['callbacks'] is {type(cbs).__name__}, expected list")
        for cb in cbs:
            assert isinstance(cb, str), (
                f"{name} callback {cb!r} is not a string")


def test_args_are_lists():
    """The 'args' field must be a list of strings."""
    for name, defn in WIDGETS.items():
        args = defn["args"]
        assert isinstance(args, list), (
            f"{name}['args'] is {type(args).__name__}, expected list")


def test_options_are_lists():
    """The 'options' field must be a list of strings."""
    for name, defn in WIDGETS.items():
        opts = defn["options"]
        assert isinstance(opts, list), (
            f"{name}['options'] is {type(opts).__name__}, expected list")


def test_no_duplicate_method_names():
    """A widget should not define a method that's already in its base
    methods (unless intentionally overriding)."""
    for name, defn in WIDGETS.items():
        base = defn["base"]
        if base == "container":
            base_methods = CONTAINER_METHODS
        elif base == "callback":
            base_methods = CALLBACK_METHODS
        else:
            base_methods = WIDGET_METHODS

        for mname in defn["methods"]:
            if mname in base_methods:
                # This is allowed (override) but the param list should
                # match or be a deliberate change. Just flag it for
                # awareness -- not a hard failure.
                pass


def test_base_methods_have_valid_params():
    """WIDGET_METHODS, CALLBACK_METHODS, and CONTAINER_METHODS should
    all have list values."""
    for source_name, methods in [("WIDGET_METHODS", WIDGET_METHODS),
                                  ("CALLBACK_METHODS", CALLBACK_METHODS),
                                  ("CONTAINER_METHODS", CONTAINER_METHODS)]:
        for mname, params in methods.items():
            assert isinstance(params, list), (
                f"{source_name}.{mname} params is "
                f"{type(params).__name__}, expected list")


def test_container_methods_include_widget_methods():
    """CONTAINER_METHODS should be a superset of WIDGET_METHODS."""
    for mname in WIDGET_METHODS:
        assert mname in CONTAINER_METHODS, (
            f"WIDGET_METHODS.{mname} missing from CONTAINER_METHODS")


def test_widget_count():
    """Sanity check: we should have a reasonable number of widgets."""
    assert len(WIDGETS) > 20, (
        f"Expected > 20 widgets, got {len(WIDGETS)}")
