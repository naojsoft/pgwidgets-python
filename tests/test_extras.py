"""
Tests for pgwidgets.extras subpackage.

Verifies that the extras modules import cleanly and expose their
documented public API.
"""


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


def test_extras_package_importable():
    """The pgwidgets.extras package itself should be importable."""
    import pgwidgets.extras
    assert pgwidgets.extras.__doc__  # has a docstring
