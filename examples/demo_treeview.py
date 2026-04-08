#!/usr/bin/env python3
"""
TreeView demo — synchronous pgwidgets.

Run this script and open the URL it prints in a browser.
"""

from pgwidgets.sync import Application

app = Application()
app.start()
W = app.get_widgets()

print("Waiting for browser connection...")
app.wait_for_connection()
print("Connected!")

# Build the UI
top = W.TopLevel(title="TreeView Demo", resizable=True)
top.resize(600, 500)

vbox = W.VBox(spacing=6, padding=8)

status = W.Label("Select an item.")

# -- Tree example --
tree = W.TreeView(
    columns=[
        "Name",
        "Type",
        {"label": "Size (KB)", "type": "number"},
    ],
    selection_mode="multi",
    alternate_row_colors=True,
)

tree.set_tree([
    {"values": ["Documents", "Folder", ""], "children": [
        {"values": ["report.pdf", "PDF", 2400]},
        {"values": ["notes.txt", "Text", 12]},
        {"values": ["Presentations", "Folder", ""], "children": [
            {"values": ["slides.pptx", "PowerPoint", 5100]},
            {"values": ["demo.key", "Keynote", 8300]},
        ]},
    ]},
    {"values": ["Pictures", "Folder", ""], "children": [
        {"values": ["photo1.jpg", "JPEG", 3200]},
        {"values": ["photo2.png", "PNG", 1800]},
        {"values": ["Vacation", "Folder", ""], "children": [
            {"values": ["beach.jpg", "JPEG", 4100]},
            {"values": ["sunset.jpg", "JPEG", 3900]},
            {"values": ["mountains.jpg", "JPEG", 5200]},
        ]},
    ]},
    {"values": ["Music", "Folder", ""], "children": [
        {"values": ["song1.mp3", "MP3", 4500]},
        {"values": ["song2.flac", "FLAC", 32000]},
    ]},
])

def on_selected(items):
    if len(items) == 1:
        status.set_text(f"Selected: {items[0]['values'][0]}")
    else:
        status.set_text(f"Selected: {len(items)} items")

tree.on("selected", on_selected)
tree.on("activated", lambda values: status.set_text(f"Activated: {values[0]}"))

# -- Buttons --
hbox = W.HBox(spacing=4)

btn_expand = W.Button("Expand All")
btn_expand.on("activated", lambda: tree.expand_all())
btn_collapse = W.Button("Collapse All")
btn_collapse.on("activated", lambda: tree.collapse_all())
hbox.add_widget(btn_expand, 0)
hbox.add_widget(btn_collapse, 0)
hbox.add_widget(W.Label("Click column headers to sort."), 0)

vbox.add_widget(hbox, 0)
vbox.add_widget(tree, 1)
vbox.add_widget(status, 0)

top.set_widget(vbox)
top.show()

print("UI built. Interact with the browser window.")
app.run()
