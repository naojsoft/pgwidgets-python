#!/usr/bin/env python3
"""
TreeView demo — synchronous pgwidgets.

Run this script and open the URL it prints in a browser.
"""

import logging
from pgwidgets.sync import Application

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pgwidgets")

app = Application(logger=logger)


@app.on_connect
def on_session(session):
    Widgets = session.get_widgets()

    # Build the UI
    top = Widgets.TopLevel(title="TreeView Demo", resizable=True)
    top.resize(600, 500)

    vbox = Widgets.VBox(spacing=6, padding=8)

    status = Widgets.Label("Select an item.")

    # -- Tree example --  (dict-tree format)
    tree = Widgets.TreeView(
        columns=[
            {"label": "Name",      "key": "NAME", "type": "string"},
            {"label": "Type",      "key": "TYPE", "type": "string"},
            {"label": "Size (KB)", "key": "SIZE", "type": "integer"},
        ],
        selection_mode="multiple",
        alternate_row_colors=True,
        sortable=True,
    )

    # Interior nodes use their dict key as their first-column label
    # (no NAME field needed).  Leaves carry their own column data.
    tree.set_tree({
        "Documents": {
            "report.pdf": {"TYPE": "PDF",  "SIZE": 2400},
            "notes.txt":  {"TYPE": "Text", "SIZE": 12},
            "Presentations": {
                "slides.pptx": {"TYPE": "PowerPoint", "SIZE": 5100},
                "demo.key":    {"TYPE": "Keynote",    "SIZE": 8300},
            },
        },
        "Pictures": {
            "photo1.jpg": {"TYPE": "JPEG", "SIZE": 3200},
            "photo2.png": {"TYPE": "PNG",  "SIZE": 1800},
            "Vacation": {
                "beach.jpg":     {"TYPE": "JPEG", "SIZE": 4100},
                "sunset.jpg":    {"TYPE": "JPEG", "SIZE": 3900},
                "mountains.jpg": {"TYPE": "JPEG", "SIZE": 5200},
            },
        },
        "Music": {
            "song1.mp3":  {"TYPE": "MP3",  "SIZE": 4500},
            "song2.flac": {"TYPE": "FLAC", "SIZE": 32000},
        },
    })

    def on_selected(items):
        if len(items) == 1:
            status.set_text(f"Selected: {items[0]['path']}")
        else:
            status.set_text(f"Selected: {len(items)} items")

    tree.on("selected", on_selected)
    tree.on("activated",
            lambda values, path: status.set_text(f"Activated: {path}"))

    # -- Buttons --
    hbox = Widgets.HBox(spacing=4)

    btn_expand = Widgets.Button("Expand All")
    btn_expand.on("activated", lambda: tree.expand_all())
    btn_collapse = Widgets.Button("Collapse All")
    btn_collapse.on("activated", lambda: tree.collapse_all())
    hbox.add_widget(btn_expand, 0)
    hbox.add_widget(btn_collapse, 0)
    hbox.add_widget(Widgets.Label("Click column headers to sort."), 0)

    vbox.add_widget(hbox, 0)
    vbox.add_widget(tree, 1)
    vbox.add_widget(status, 0)

    top.set_widget(vbox)
    top.show()

    print(f"Session {session.id}: UI built.")


app.run()
