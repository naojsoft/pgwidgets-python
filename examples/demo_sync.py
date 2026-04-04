#!/usr/bin/env python3
"""
Synchronous pgwidgets demo.

Run this script and open the URL it prints in a browser.
"""

from pgwidgets.sync import Application

app = Application()
W = app.get_widgets()

print("Waiting for browser connection...")
app.wait_for_connection()
print("Connected!")

# Build the UI
top = W.TopLevel(title="Sync Demo", resizable=True)
top.resize(400, 300)

vbox = W.VBox(spacing=8, padding=10)

status = W.Label("Click a button!")

hbox = W.HBox(spacing=6)
btn_hello = W.Button("Hello")
btn_world = W.Button("World")
btn_clear = W.Button("Clear")
hbox.add_widget(btn_hello, 0)
hbox.add_widget(btn_world, 0)
hbox.add_widget(btn_clear, 0)

entry = W.TextEntry(text="Type here", linehistory=5)
slider = W.Slider(min=0, max=100, value=50, track=True)

vbox.add_widget(hbox, 0)
vbox.add_widget(entry, 0)
vbox.add_widget(slider, 0)
vbox.add_widget(status, 1)

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

print("UI built. Interact with the browser window.")
app.run()
