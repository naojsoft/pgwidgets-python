"""
Asynchronous pgwidgets API.

Usage:
    from pgwidgets.async_ import Application

    app = Application()
    W = app.get_widgets()

    top = await W.TopLevel(title="Hello", resizable=True)
    top.resize(400, 300)

    btn = await W.Button("Click me")
    await btn.on("activated", my_handler)

    await top.set_widget(btn)
    await top.show()
    await app.run()
"""

from pgwidgets.async_.application import Application

__all__ = ["Application"]
