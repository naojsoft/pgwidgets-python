"""
Synchronous pgwidgets API.

Usage:
    from pgwidgets.sync import Application

    app = Application()
    W = app.get_widgets()

    top = W.TopLevel(title="Hello", resizable=True)
    top.resize(400, 300)

    btn = W.Button("Click me")
    btn.on("activated", lambda: print("clicked!"))

    top.set_widget(btn)
    top.show()
    app.run()
"""

from pgwidgets.sync.application import Application

__all__ = ["Application"]
