#!/usr/bin/env python3
"""
Synchronous pgwidgets demo.

Run this script and open the URL it prints in a browser.
"""

import base64
from pgwidgets.sync import Application

app = Application(max_sessions=4)


@app.on_connect
def on_session(session):
    Widgets = session.get_widgets()

    # Build the UI
    top = Widgets.TopLevel(title="Sync Demo", resizable=True)
    top.resize(400, 300)

    vbox = Widgets.VBox(spacing=8, padding=10)

    status = Widgets.Label("Click a button!")

    hbox = Widgets.HBox(spacing=6)
    btn_hello = Widgets.Button("Hello")
    btn_world = Widgets.Button("World")
    btn_clear = Widgets.Button("Clear")
    hbox.add_widget(btn_hello, 0)
    hbox.add_widget(btn_world, 0)
    hbox.add_widget(btn_clear, 0)

    entry = Widgets.TextEntry(text="Type here", linehistory=5)
    slider = Widgets.Slider(min=0, max=100, value=50, track=True)

    # Drag-drop demo: drop text or a file onto the label to load into textarea.
    ta = Widgets.TextArea("Drag text or a file onto the drop zone below.")
    drop_label = Widgets.Label("Drop here")
    drop_label.set_halign("center")
    drop_label.set_color("#e8f0fe", "#4a86c8")
    drop_label.set_font(None, 14)

    vbox.add_widget(hbox, 0)
    vbox.add_widget(entry, 0)
    vbox.add_widget(slider, 0)
    vbox.add_widget(ta, 1)
    vbox.add_widget(drop_label, 0)
    vbox.add_widget(status, 0)

    top.set_widget(vbox)
    top.show()

    # Wire up callbacks
    btn_hello.on("activated", lambda: status.set_text("Hello!"))
    btn_world.on("activated", lambda: status.set_text("World!"))

    def on_clear():
        status.set_text("")
        entry.set_text("")

    btn_clear.on("activated", on_clear)
    entry.on("activated", lambda text: status.set_text(f"Entered: {text}"))
    slider.on("activated", lambda value: status.set_text(f"Slider: {value}"))

    def on_drop(evt):
        if evt.get("files"):
            f = evt["files"][0]
            if f.get("data"):
                b64 = f["data"].split(",", 1)[1]
                text = base64.b64decode(b64).decode("utf-8", errors="replace")
                ta.set_text(text)
                status.set_text(f"Loaded file: {f['name']}")
        elif evt.get("text"):
            ta.set_text(evt["text"])
            status.set_text("Loaded dropped text")

    drop_label.on("drag-drop", on_drop)

    print(f"Session {session.id}: UI built.")


app.run()
