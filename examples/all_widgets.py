#!/usr/bin/env python3
"""
All Widgets demo for pgwidgets sync API.

Uses an MDI workspace with a picker to open demos for each widget
type.  Interact with widgets, then press F5 to test reconstruction.

Run:  python examples/all_widgets.py
"""

import logging
from pgwidgets.sync import Application

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pgwidgets")

app = Application(max_sessions=4, logger=logger)


@app.on_connect
def on_session(session):
    W = session.get_widgets()

    top = W.TopLevel(title="All Widgets Demo", resizable=True)
    top.resize(950, 700)

    vbox = W.VBox()

    # -- Menu bar --
    menubar = W.MenuBar()
    windows_menu = W.Menu()
    cascade_action = windows_menu.add_name("Cascade")
    tile_action = windows_menu.add_name("Tile")
    menubar.add_menu(windows_menu, "Windows")
    vbox.add_widget(menubar, 0)

    # -- MDI area --
    mdi = W.MDIWidget()
    vbox.add_widget(mdi, 1)

    cascade_action.on("activated", lambda: mdi.cascade_windows())
    tile_action.on("activated", lambda: mdi.tile_windows())

    # -- Status bar --
    status = W.Label("Select a widget from the picker to see a demo. "
                     "Press F5 to test reconstruction.")
    status.set_color("#e8f0fe", "#333")
    status.set_padding([4, 8, 4, 8])
    vbox.add_widget(status, 0)

    # -- Picker window --
    picker_content = W.VBox(spacing=6, padding=8)
    picker_label = W.TextEntry(text="Pick a widget:", editable=False)
    picker_content.add_widget(picker_label, 0)

    widget_names = [
        "Button", "CheckBox", "ComboBox", "Dial",
        "Expander", "Frame", "GridBox", "Label",
        "ProgressBar", "RadioButton", "ScrollArea", "ScrollBar",
        "Slider", "SpinBox", "Splitter", "StackWidget",
        "TabWidget", "TableView", "TextArea", "TextEntry",
        "TextEntrySet", "ToggleButton", "ToolBar", "TreeView",
        "VBox/HBox",
    ]

    picker = W.ComboBox(dropdown_limit=10)
    for name in widget_names:
        picker.append_text(name)
    picker.set_index(0)
    picker_content.add_widget(picker, 0)

    go_btn = W.Button("Go!")
    picker_content.add_widget(go_btn, 0)
    picker_content.add_widget(W.Label(""), 1)

    mdi.add_widget(picker_content,
                   {"title": "Widget Picker", "width": 220, "height": 180})

    # -- Demo creation --
    demo_count = 0

    def next_position():
        nonlocal demo_count
        demo_count += 1
        return (40 + (demo_count % 6) * 25, 20 + (demo_count % 6) * 25)

    def make_demo(name):
        pos = next_position()

        if name == "Button":
            content = W.VBox(spacing=6, padding=8)
            hbox = W.HBox(spacing=6)
            lbl = W.Label("")
            btn_a = W.Button("Button A")
            btn_a.on("activated",
                     lambda: lbl.set_text("Button A clicked"))
            btn_b = W.Button("Button B")
            btn_b.on("activated",
                     lambda: lbl.set_text("Button B clicked"))
            hbox.add_widget(btn_a, 0)
            hbox.add_widget(btn_b, 0)
            content.add_widget(hbox, 0)
            content.add_widget(lbl, 1)
            mdi.add_widget(content,
                           {"title": "Button", "width": 300, "height": 120,
                            "x": pos[0], "y": pos[1]})

        elif name == "CheckBox":
            content = W.VBox(spacing=4, padding=8)
            lbl = W.Label("")
            cb1 = W.CheckBox("Option 1")
            cb1.on("activated",
                   lambda val: lbl.set_text(
                       f"Option 1: {'ON' if val else 'OFF'}"))
            cb2 = W.CheckBox("Option 2")
            cb2.on("activated",
                   lambda val: lbl.set_text(
                       f"Option 2: {'ON' if val else 'OFF'}"))
            cb3 = W.CheckBox("Option 3")
            cb3.on("activated",
                   lambda val: lbl.set_text(
                       f"Option 3: {'ON' if val else 'OFF'}"))
            content.add_widget(cb1, 0)
            content.add_widget(cb2, 0)
            content.add_widget(cb3, 0)
            content.add_widget(lbl, 1)
            mdi.add_widget(content,
                           {"title": "CheckBox", "width": 250, "height": 160,
                            "x": pos[0], "y": pos[1]})

        elif name == "ComboBox":
            content = W.VBox(spacing=6, padding=8)
            lbl = W.Label("")
            content.add_widget(W.Label("Pick-only:"), 0)
            combo1 = W.ComboBox()
            for f in ["Apple", "Banana", "Cherry", "Date", "Elderberry"]:
                combo1.append_text(f)
            combo1.set_index(0)
            combo1.on("activated",
                      lambda idx, text: lbl.set_text(f"Picked: {text}"))
            content.add_widget(combo1, 0)
            content.add_widget(W.Label("Editable:"), 0)
            combo2 = W.ComboBox(editable=True, dropdown_limit=5)
            for c in ["Red", "Orange", "Yellow", "Green", "Blue",
                       "Indigo", "Violet"]:
                combo2.append_text(c)
            combo2.on("activated",
                      lambda idx, text: lbl.set_text(f"Entered: {text}"))
            content.add_widget(combo2, 0)
            content.add_widget(lbl, 1)
            mdi.add_widget(content,
                           {"title": "ComboBox", "width": 280, "height": 200,
                            "x": pos[0], "y": pos[1]})

        elif name == "Dial":
            content = W.HBox(spacing=8, padding=8)
            lbl = W.Label("50")
            dial1 = W.Dial(min=0, max=100, value=50, track=True)
            dial1.on("activated", lambda val: lbl.set_text(str(val)))
            dial2 = W.Dial(min=0, max=100, value=25)
            dial2.on("activated", lambda val: lbl.set_text(str(val)))
            content.add_widget(dial1, 0)
            content.add_widget(dial2, 0)
            content.add_widget(lbl, 1)
            mdi.add_widget(content,
                           {"title": "Dial", "width": 320, "height": 160,
                            "x": pos[0], "y": pos[1]})

        elif name == "Expander":
            content = W.VBox(spacing=4, padding=8)
            exp1 = W.Expander(title="Section A", collapsible=True)
            exp1.set_widget(W.Label("Content of section A."))
            exp2 = W.Expander(title="Section B", collapsible=True)
            exp2.set_widget(W.Label("Content of section B."))
            content.add_widget(exp1, 0)
            content.add_widget(exp2, 0)
            content.add_widget(W.Label(""), 1)
            mdi.add_widget(content,
                           {"title": "Expander", "width": 280, "height": 180,
                            "x": pos[0], "y": pos[1]})

        elif name == "Frame":
            content = W.VBox(spacing=6, padding=8)
            frame1 = W.Frame(title="Titled Frame")
            frame1.set_widget(W.Label("Content inside a frame."))
            frame2 = W.Frame(title="Another Frame")
            frame2.set_widget(W.Label("More framed content."))
            content.add_widget(frame1, 1)
            content.add_widget(frame2, 1)
            mdi.add_widget(content,
                           {"title": "Frame", "width": 280, "height": 200,
                            "x": pos[0], "y": pos[1]})

        elif name == "GridBox":
            content = W.VBox(padding=8, spacing=6)
            lbl = W.Label("")
            grid = W.GridBox(rows=3, columns=3)
            for r in range(3):
                for c in range(3):
                    btn = W.Button(f"({r},{c})")
                    btn.on("activated",
                           lambda _r=r, _c=c: lbl.set_text(
                               f"Clicked row={_r} col={_c}"))
                    grid.add_widget(btn, r, c)
            content.add_widget(grid, 1)
            content.add_widget(lbl, 0)
            mdi.add_widget(content,
                           {"title": "GridBox", "width": 280, "height": 200,
                            "x": pos[0], "y": pos[1]})

        elif name == "Label":
            content = W.VBox(spacing=6, padding=8)
            lbl1 = W.Label("Default label")
            lbl2 = W.Label("Centered, colored")
            lbl2.set_halign("center")
            lbl2.set_color("#eef", "darkblue")
            lbl3 = W.Label("Monospace, bold")
            lbl3.set_font("monospace", 12, "bold")
            content.add_widget(lbl1, 0)
            content.add_widget(lbl2, 0)
            content.add_widget(lbl3, 0)
            content.add_widget(W.Label(""), 1)
            mdi.add_widget(content,
                           {"title": "Label", "width": 260, "height": 150,
                            "x": pos[0], "y": pos[1]})

        elif name == "ProgressBar":
            content = W.VBox(spacing=6, padding=8)
            pb = W.ProgressBar()
            pb.set_value(0.65)
            slider = W.Slider(min=0, max=100, value=65, track=True)
            slider.on("activated", lambda val: pb.set_value(val / 100))
            content.add_widget(W.Label("Drag slider to change:"), 0)
            content.add_widget(slider, 0)
            content.add_widget(pb, 0)
            content.add_widget(W.Label(""), 1)
            mdi.add_widget(content,
                           {"title": "ProgressBar", "width": 320,
                            "height": 150,
                            "x": pos[0], "y": pos[1]})

        elif name == "RadioButton":
            content = W.VBox(spacing=4, padding=8)
            lbl = W.Label("")
            rb1 = W.RadioButton("Choice A")
            rb1.on("activated",
                   lambda val: lbl.set_text("Selected: A") if val else None)
            rb2 = W.RadioButton("Choice B", group=rb1)
            rb2.on("activated",
                   lambda val: lbl.set_text("Selected: B") if val else None)
            rb3 = W.RadioButton("Choice C", group=rb1)
            rb3.on("activated",
                   lambda val: lbl.set_text("Selected: C") if val else None)
            rb1.set_state(True)
            content.add_widget(rb1, 0)
            content.add_widget(rb2, 0)
            content.add_widget(rb3, 0)
            content.add_widget(lbl, 1)
            mdi.add_widget(content,
                           {"title": "RadioButton", "width": 250,
                            "height": 160,
                            "x": pos[0], "y": pos[1]})

        elif name == "ScrollArea":
            big = W.VBox(spacing=4, padding=8)
            for i in range(30):
                row = W.HBox(spacing=4)
                for j in range(8):
                    lbl = W.Label(f"Item {i * 8 + j}")
                    lbl.set_padding([2, 6, 2, 6])
                    lbl.set_color(
                        "#f8f8f8" if i % 2 == 0 else "#fff", "#333")
                    row.add_widget(lbl, 0)
                big.add_widget(row, 0)
            scroll = W.ScrollArea()
            scroll.set_widget(big)
            mdi.add_widget(scroll,
                           {"title": "ScrollArea", "width": 320,
                            "height": 200,
                            "x": pos[0], "y": pos[1]})

        elif name == "ScrollBar":
            content = W.VBox(spacing=8, padding=8)
            lbl = W.Label("0%")
            content.add_widget(W.Label("Horizontal:"), 0)
            hsb = W.ScrollBar(orientation="horizontal")
            hsb.set_thumb_percent(0.2)
            hsb.on("activated",
                   lambda pct: lbl.set_text(f"{int(pct * 100)}%"))
            content.add_widget(hsb, 0)
            hbox = W.HBox(spacing=8)
            hbox.add_widget(W.Label("Vertical:"), 0)
            vsb = W.ScrollBar(orientation="vertical")
            vsb.set_thumb_percent(0.3)
            vsb.on("activated",
                   lambda pct: lbl.set_text(f"{int(pct * 100)}%"))
            hbox.add_widget(vsb, 0)
            hbox.add_widget(lbl, 1)
            content.add_widget(hbox, 1)
            mdi.add_widget(content,
                           {"title": "ScrollBar", "width": 280,
                            "height": 200,
                            "x": pos[0], "y": pos[1]})

        elif name == "Slider":
            content = W.VBox(spacing=6, padding=8)
            lbl = W.Label("")
            sl1 = W.Slider(min=0, max=100, value=50)
            sl1.on("activated",
                   lambda val: lbl.set_text(f"Integer: {val}"))
            sl2 = W.Slider(min=0, max=1, step=0.01, value=0.5,
                           dtype="float", track=True)
            sl2.on("activated",
                   lambda val: lbl.set_text(f"Float: {val}"))
            content.add_widget(W.Label("Integer (0-100):"), 0)
            content.add_widget(sl1, 0)
            content.add_widget(W.Label("Float tracking (0-1):"), 0)
            content.add_widget(sl2, 0)
            content.add_widget(lbl, 1)
            mdi.add_widget(content,
                           {"title": "Slider", "width": 320, "height": 180,
                            "x": pos[0], "y": pos[1]})

        elif name == "SpinBox":
            content = W.VBox(spacing=6, padding=8)
            lbl = W.Label("")
            content.add_widget(W.Label("Integer (0-100):"), 0)
            sp1 = W.SpinBox(min=0, max=100, step=1, value=50)
            sp1.on("activated", lambda val: lbl.set_text(f"Int: {val}"))
            content.add_widget(sp1, 0)
            content.add_widget(W.Label("Float (0-1):"), 0)
            sp2 = W.SpinBox(min=0, max=1, step=0.05, value=0.5,
                            dtype="float")
            sp2.on("activated", lambda val: lbl.set_text(f"Float: {val}"))
            content.add_widget(sp2, 0)
            content.add_widget(lbl, 1)
            mdi.add_widget(content,
                           {"title": "SpinBox", "width": 280, "height": 180,
                            "x": pos[0], "y": pos[1]})

        elif name == "Splitter":
            content = W.VBox(padding=2, spacing=4)
            lbl = W.Label("Drag the handles to resize panes.")
            hsplit = W.Splitter(orientation="horizontal")
            p1 = W.Label("Left")
            p1.set_halign("center")
            p1.set_color("#e8f0fe", "#333")
            p2 = W.Label("Center")
            p2.set_halign("center")
            p2.set_color("#fef7e0", "#333")
            p3 = W.Label("Right")
            p3.set_halign("center")
            p3.set_color("#e8fee8", "#333")
            hsplit.add_widget(p1)
            hsplit.add_widget(p2)
            hsplit.add_widget(p3)
            content.add_widget(hsplit, 1)
            content.add_widget(lbl, 0)
            mdi.add_widget(content,
                           {"title": "Splitter", "width": 360,
                            "height": 180,
                            "x": pos[0], "y": pos[1]})

        elif name == "StackWidget":
            content = W.VBox(spacing=6, padding=8)
            lbl = W.Label("Page 1 visible")
            stack = W.StackWidget()
            page1 = W.VBox(padding=8)
            page1_lbl = W.Label("Stack page 1")
            page1_lbl.set_color("#e8f0fe", "#333")
            page1_lbl.set_halign("center")
            page1.add_widget(page1_lbl, 1)
            page2 = W.VBox(padding=8)
            page2_lbl = W.Label("Stack page 2")
            page2_lbl.set_color("#fef7e0", "#333")
            page2_lbl.set_halign("center")
            page2.add_widget(page2_lbl, 1)
            page3 = W.VBox(padding=8)
            page3_lbl = W.Label("Stack page 3")
            page3_lbl.set_color("#e8fee8", "#333")
            page3_lbl.set_halign("center")
            page3.add_widget(page3_lbl, 1)
            stack.add_widget(page1, {"title": "Page 1"})
            stack.add_widget(page2, {"title": "Page 2"})
            stack.add_widget(page3, {"title": "Page 3"})
            btn_row = W.HBox(spacing=4)
            for i, (pg, nm) in enumerate([(page1, "Page 1"),
                                          (page2, "Page 2"),
                                          (page3, "Page 3")]):
                btn = W.Button(nm)
                btn.on("activated",
                       lambda _pg=pg, _nm=nm: (
                           stack.show_widget(_pg),
                           lbl.set_text(f"{_nm} visible")))
                btn_row.add_widget(btn, 0)
            content.add_widget(btn_row, 0)
            content.add_widget(stack, 1)
            content.add_widget(lbl, 0)
            mdi.add_widget(content,
                           {"title": "StackWidget", "width": 300,
                            "height": 200,
                            "x": pos[0], "y": pos[1]})

        elif name == "TabWidget":
            content = W.VBox(spacing=6, padding=8)
            lbl = W.Label("")
            tabs = W.TabWidget(closable=True, reorderable=True)
            for n in range(1, 4):
                pg = W.VBox(padding=8)
                pg_lbl = W.Label(f"Content of tab {n}")
                pg_lbl.set_halign("center")
                colors = ["#e8f0fe", "#fef7e0", "#e8fee8"]
                pg_lbl.set_color(colors[n - 1], "#333")
                pg.add_widget(pg_lbl, 1)
                tabs.add_widget(pg, {"title": f"Tab {n}"})
            tabs.on("page-switch",
                    lambda child, idx: lbl.set_text(f"Switched to tab {idx}"))
            add_btn = W.Button("Add Tab")
            tab_counter = [3]
            def on_add_tab():
                tab_counter[0] += 1
                n = tab_counter[0]
                pg = W.VBox(padding=8)
                pg_lbl = W.Label(f"Content of tab {n}")
                pg_lbl.set_halign("center")
                pg.add_widget(pg_lbl, 1)
                tabs.add_widget(pg, {"title": f"Tab {n}"})
                lbl.set_text(f"Added tab {n}")
            add_btn.on("activated", on_add_tab)
            content.add_widget(tabs, 1)
            btn_row = W.HBox(spacing=6)
            btn_row.add_widget(add_btn, 0)
            btn_row.add_widget(lbl, 1)
            content.add_widget(btn_row, 0)
            mdi.add_widget(content,
                           {"title": "TabWidget", "width": 350,
                            "height": 220,
                            "x": pos[0], "y": pos[1]})

        elif name == "TableView":
            content = W.VBox(spacing=4, padding=4)
            lbl = W.Label("")
            table = W.TableView(
                columns=[
                    {"label": "Name",       "key": "NAME",
                     "type": "string"},
                    {"label": "Department", "key": "DEPT",
                     "type": "string"},
                    {"label": "Salary",     "key": "SALARY",
                     "type": "integer"},
                ],
                selection_mode="multiple",
                alternate_row_colors=True,
                sortable=True,
            )
            table.set_data([
                {"NAME": "Alice", "DEPT": "Engineering", "SALARY": 95000},
                {"NAME": "Bob",   "DEPT": "Marketing",   "SALARY": 72000},
                {"NAME": "Carol", "DEPT": "Engineering", "SALARY": 102000},
                {"NAME": "Dave",  "DEPT": "Sales",       "SALARY": 68000},
                {"NAME": "Eve",   "DEPT": "Engineering", "SALARY": 98000},
                {"NAME": "Frank", "DEPT": "Marketing",   "SALARY": 75000},
                {"NAME": "Grace", "DEPT": "Sales",       "SALARY": 71000},
                {"NAME": "Heidi", "DEPT": "Engineering", "SALARY": 110000},
            ])
            table.on("selected",
                     lambda items: lbl.set_text(
                         f"Selected: {items[0]['values'].get('NAME', '')}"
                         if len(items) == 1
                         else f"Selected: {len(items)} rows"))
            table.on("activated",
                     lambda values, path: lbl.set_text(
                         f"Activated: {values.get('NAME', '')}"))
            hbox = W.HBox(spacing=4)
            btn_add = W.Button("Add Row")
            row_counter = [8]
            def on_add_row():
                row_counter[0] += 1
                table.append_row({
                    "NAME": f"Person {row_counter[0]}",
                    "DEPT": "New", "SALARY": 60000,
                })
            btn_add.on("activated", on_add_row)
            btn_sort = W.Button("Sort by Name")
            btn_sort.on("activated", lambda: table.sort_by_column("NAME"))
            hbox.add_widget(btn_add, 0)
            hbox.add_widget(btn_sort, 0)
            hbox.add_widget(lbl, 1)
            content.add_widget(hbox, 0)
            content.add_widget(table, 1)
            mdi.add_widget(content,
                           {"title": "TableView", "width": 420,
                            "height": 280,
                            "x": pos[0], "y": pos[1]})

        elif name == "TextArea":
            ta = W.TextArea(
                "This is a multi-line text area.\n\n"
                "Edit this text, then press F5.\n"
                "The contents should be preserved.")
            mdi.add_widget(ta,
                           {"title": "TextArea", "width": 320,
                            "height": 200,
                            "x": pos[0], "y": pos[1]})

        elif name == "TextEntry":
            content = W.VBox(spacing=6, padding=8)
            lbl = W.Label("Press Enter to activate.")
            entry = W.TextEntry(text="Type here", linehistory=10)
            entry.on("activated",
                     lambda text: lbl.set_text(f"Entered: {text}"))
            content.add_widget(entry, 0)
            content.add_widget(W.Label("Password:"), 0)
            pw = W.TextEntry(password=True)
            pw.on("activated",
                  lambda text: lbl.set_text(f"Password: {text}"))
            content.add_widget(pw, 0)
            content.add_widget(lbl, 1)
            mdi.add_widget(content,
                           {"title": "TextEntry", "width": 300,
                            "height": 160,
                            "x": pos[0], "y": pos[1]})

        elif name == "TextEntrySet":
            content = W.VBox(spacing=6, padding=8)
            lbl = W.Label("Press Enter or click Set.")
            tes = W.TextEntrySet(text="Set", value="Hello",
                                 linehistory=5)
            tes.on("activated",
                   lambda text: lbl.set_text(f"Value: {text}"))
            content.add_widget(tes, 0)
            content.add_widget(lbl, 1)
            mdi.add_widget(content,
                           {"title": "TextEntrySet", "width": 300,
                            "height": 120,
                            "x": pos[0], "y": pos[1]})

        elif name == "ToggleButton":
            content = W.VBox(spacing=6, padding=8)
            lbl = W.Label("")
            content.add_widget(W.Label("Independent toggles:"), 0)
            hbox1 = W.HBox(spacing=4)
            tb1 = W.ToggleButton("Bold")
            tb1.on("activated",
                   lambda st: lbl.set_text(
                       f"Bold: {'on' if st else 'off'}"))
            tb2 = W.ToggleButton("Italic")
            tb2.on("activated",
                   lambda st: lbl.set_text(
                       f"Italic: {'on' if st else 'off'}"))
            hbox1.add_widget(tb1, 0)
            hbox1.add_widget(tb2, 0)
            content.add_widget(hbox1, 0)
            content.add_widget(W.Label("Grouped (exclusive):"), 0)
            hbox2 = W.HBox(spacing=4)
            tg1 = W.ToggleButton("Left")
            tg2 = W.ToggleButton("Center", group=tg1)
            tg3 = W.ToggleButton("Right", group=tg1)
            tg1.on("activated",
                   lambda st: lbl.set_text("Align: Left") if st else None)
            tg2.on("activated",
                   lambda st: lbl.set_text("Align: Center") if st else None)
            tg3.on("activated",
                   lambda st: lbl.set_text("Align: Right") if st else None)
            hbox2.add_widget(tg1, 0)
            hbox2.add_widget(tg2, 0)
            hbox2.add_widget(tg3, 0)
            content.add_widget(hbox2, 0)
            content.add_widget(lbl, 1)
            mdi.add_widget(content,
                           {"title": "ToggleButton", "width": 300,
                            "height": 180,
                            "x": pos[0], "y": pos[1]})

        elif name == "ToolBar":
            content = W.VBox()
            lbl = W.Label("Click toolbar items.")
            lbl.set_padding(8)
            tb = W.ToolBar()
            act1 = tb.add_action({"text": "New"})
            act1.on("activated", lambda: lbl.set_text("New clicked"))
            act2 = tb.add_action({"text": "Open"})
            act2.on("activated", lambda: lbl.set_text("Open clicked"))
            act3 = tb.add_action({"text": "Save"})
            act3.on("activated", lambda: lbl.set_text("Save clicked"))
            tb.add_separator()
            tog1 = tb.add_action({"text": "B", "toggle": True})
            tog1.on("activated",
                    lambda st: lbl.set_text(
                        f"Bold: {'on' if st else 'off'}"))
            tog2 = tb.add_action({"text": "I", "toggle": True})
            tog2.on("activated",
                    lambda st: lbl.set_text(
                        f"Italic: {'on' if st else 'off'}"))
            content.add_widget(tb, 0)
            content.add_widget(lbl, 1)
            mdi.add_widget(content,
                           {"title": "ToolBar", "width": 350,
                            "height": 120,
                            "x": pos[0], "y": pos[1]})

        elif name == "TreeView":
            content = W.VBox(spacing=4, padding=4)
            lbl = W.Label("")
            tree = W.TreeView(
                columns=[
                    {"label": "Name", "key": "NAME", "type": "string"},
                    {"label": "Type", "key": "TYPE", "type": "string"},
                    {"label": "Size (KB)", "key": "SIZE",
                     "type": "integer"},
                ],
                selection_mode="multiple",
                alternate_row_colors=True,
                sortable=True,
            )
            tree.set_tree({
                "Documents": {
                    "report.pdf": {"TYPE": "PDF",  "SIZE": 2400},
                    "notes.txt":  {"TYPE": "Text", "SIZE": 12},
                    "Presentations": {
                        "slides.pptx": {"TYPE": "PowerPoint",
                                        "SIZE": 5100},
                        "demo.key":    {"TYPE": "Keynote",
                                        "SIZE": 8300},
                    },
                },
                "Pictures": {
                    "photo1.jpg": {"TYPE": "JPEG", "SIZE": 3200},
                    "photo2.png": {"TYPE": "PNG",  "SIZE": 1800},
                },
                "Music": {
                    "song1.mp3":  {"TYPE": "MP3",  "SIZE": 4500},
                    "song2.flac": {"TYPE": "FLAC", "SIZE": 32000},
                },
            })
            tree.on("selected",
                    lambda items: lbl.set_text(
                        f"Selected: {items[0]['path']}"
                        if len(items) == 1
                        else f"Selected: {len(items)} items"))
            tree.on("activated",
                    lambda values, path: lbl.set_text(
                        f"Activated: {path}"))
            hbox = W.HBox(spacing=4)
            btn_exp = W.Button("Expand All")
            btn_exp.on("activated", lambda: tree.expand_all())
            btn_col = W.Button("Collapse All")
            btn_col.on("activated", lambda: tree.collapse_all())
            hbox.add_widget(btn_exp, 0)
            hbox.add_widget(btn_col, 0)
            hbox.add_widget(lbl, 1)
            content.add_widget(hbox, 0)
            content.add_widget(tree, 1)
            mdi.add_widget(content,
                           {"title": "TreeView", "width": 420,
                            "height": 300,
                            "x": pos[0], "y": pos[1]})

        elif name == "VBox/HBox":
            content = W.VBox(spacing=6, padding=8)
            lbl = W.Label("stretch=0 fixed, stretch=1 fills")
            hbox = W.HBox(spacing=4)
            fixed1 = W.Button("Fixed (0)")
            stretch1 = W.Label("Stretch (1)")
            stretch1.set_color("#e8f0fe", "#333")
            stretch1.set_halign("center")
            fixed2 = W.Button("Fixed (0)")
            hbox.add_widget(fixed1, 0)
            hbox.add_widget(stretch1, 1)
            hbox.add_widget(fixed2, 0)
            content.add_widget(W.Label("HBox - horizontal:"), 0)
            content.add_widget(hbox, 0)
            inner = W.VBox(spacing=4)
            top_l = W.Label("Top (stretch=0)")
            top_l.set_color("#fef7e0", "#333")
            top_l.set_halign("center")
            mid_l = W.Label("Middle (stretch=1)")
            mid_l.set_color("#e8fee8", "#333")
            mid_l.set_halign("center")
            bot_l = W.Label("Bottom (stretch=0)")
            bot_l.set_color("#fee8e8", "#333")
            bot_l.set_halign("center")
            inner.add_widget(top_l, 0)
            inner.add_widget(mid_l, 1)
            inner.add_widget(bot_l, 0)
            content.add_widget(W.Label("VBox - vertical:"), 0)
            content.add_widget(inner, 1)
            content.add_widget(lbl, 0)
            mdi.add_widget(content,
                           {"title": "VBox / HBox", "width": 360,
                            "height": 280,
                            "x": pos[0], "y": pos[1]})

        else:
            return

        status.set_text(f"Opened demo: {name}")

    def on_go():
        idx = picker.get_index()
        if idx is not None and 0 <= idx < len(widget_names):
            make_demo(widget_names[idx])

    go_btn.on("activated", on_go)

    top.set_widget(vbox)
    top.show()

    print(f"Session {session.id}: all_widgets UI built.")


app.run()
