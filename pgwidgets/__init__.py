"""
pgwidgets — Python bindings for the pgwidgets JavaScript widget library.

Usage (synchronous):
    from pgwidgets.sync import Application
    app = Application()
    W = app.get_widgets()
    top = W.TopLevel(title="Hello", resizable=True)
    ...
    app.run()

Usage (asynchronous):
    from pgwidgets.async_ import Application
    app = Application()
    W = app.get_widgets()
    top = await W.TopLevel(title="Hello", resizable=True)
    ...
    await app.run()

Version:
    import pgwidgets
    print(pgwidgets.__version__)
"""

from importlib.metadata import version as _pkg_version, PackageNotFoundError

try:
    __version__ = _pkg_version("pgwidgets")
except PackageNotFoundError:
    # Package not installed (e.g. running from a source checkout
    # without `pip install -e .`).  Fall back to a sentinel.
    __version__ = "0.0.0+unknown"
