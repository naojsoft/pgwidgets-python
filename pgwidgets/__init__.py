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
"""
