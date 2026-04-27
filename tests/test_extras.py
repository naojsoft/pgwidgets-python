"""
Tests for pgwidgets.extras subpackage.

Verifies that the extras modules import cleanly and expose their
documented public API.
"""

import os
import tempfile


def test_file_browser_import():
    """The FileBrowser class should be importable from pgwidgets.extras."""
    from pgwidgets.extras.file_browser import FileBrowser
    assert FileBrowser is not None
    assert hasattr(FileBrowser, "popup")
    assert hasattr(FileBrowser, "add_ext_filter")
    assert hasattr(FileBrowser, "clear_filters")
    assert hasattr(FileBrowser, "set_directory")
    assert hasattr(FileBrowser, "set_filename")
    assert hasattr(FileBrowser, "set_mode")
    assert hasattr(FileBrowser, "on")


def test_file_browser_default_icons_loaded():
    """The ICONS dict should have 'file', 'folder', 'parent' set
    to data: URIs at module import time."""
    from pgwidgets.extras.file_browser import ICONS
    for category in ("file", "folder", "parent"):
        assert category in ICONS, f"missing default icon: {category}"
        assert ICONS[category].startswith("data:"), (
            f"icon for {category} is not a data URI")


def test_set_icon_registers_new_category():
    """set_icon() should add a new entry to the ICONS dict."""
    from pgwidgets.extras.file_browser import ICONS, set_icon

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(b"fake png bytes")
        path = f.name
    try:
        set_icon("py", path)
        assert "py" in ICONS
        assert ICONS["py"].startswith("data:image/png;base64,")
    finally:
        os.unlink(path)


def test_extras_package_importable():
    """The pgwidgets.extras package itself should be importable."""
    import pgwidgets.extras
    assert pgwidgets.extras.__doc__  # has a docstring
