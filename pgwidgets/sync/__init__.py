"""
Synchronous pgwidgets API.

Usage:
    from pgwidgets.sync import Application

    app = Application()

    @app.on_connect
    def setup(session):
        W = session.get_widgets()
        top = W.TopLevel(title="Hello", resizable=True)
        top.resize(400, 300)
        btn = W.Button("Click me")
        btn.on("activated", lambda: print("clicked!"))
        top.set_widget(btn)
        top.show()

    app.start()
    app.run()
"""

from pgwidgets.sync.application import Application, Session

__all__ = ["Application", "Session"]
