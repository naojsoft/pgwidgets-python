#!/usr/bin/env python3
"""
All Widgets demo for pgwidgets async API.

Uses an MDI workspace with a picker to open demos for each widget type.

Run:  python examples/all_widgets_async.py
"""

import asyncio
import logging
from pgwidgets.async_ import Application

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pgwidgets")


async def main():
    app = Application(max_sessions=4, logger=logger)

    @app.on_connect
    async def on_session(session):
        W = session.get_widgets()

        top = await W.TopLevel(title="All Widgets Demo", resizable=True)
        await top.resize(950, 700)

        vbox = await W.VBox()

        # -- Menu bar --
        menubar = await W.MenuBar()
        windows_menu = await W.Menu()
        cascade_action = await windows_menu.add_name("Cascade")
        tile_action = await windows_menu.add_name("Tile")
        await menubar.add_menu(windows_menu, "Windows")
        await vbox.add_widget(menubar, 0)

        # -- MDI area --
        mdi = await W.MDIWidget()
        await vbox.add_widget(mdi, 1)

        async def on_cascade():
            await mdi.cascade_windows()
        async def on_tile():
            await mdi.tile_windows()
        await cascade_action.on("activated", on_cascade)
        await tile_action.on("activated", on_tile)

        # -- Status bar --
        status = await W.Label("Select a widget from the picker to see a demo.")
        await status.set_color("#e8f0fe", "#333")
        await status.set_padding([4, 8, 4, 8])
        await vbox.add_widget(status, 0)

        # -- Picker window --
        picker_content = await W.VBox(spacing=6, padding=8)
        picker_label = await W.TextEntry(text="Pick a widget:", editable=False)
        await picker_content.add_widget(picker_label, 0)

        widget_names = [
            "Button", "CheckBox", "ComboBox", "Dial",
            "Expander", "Frame", "GridBox", "Label",
            "ProgressBar", "RadioButton", "ScrollArea", "ScrollBar",
            "Slider", "SpinBox", "Splitter", "StackWidget",
            "TabWidget", "TableView", "TextArea", "TextEntry",
            "TextEntrySet", "ToggleButton", "ToolBar", "TreeView",
            "VBox/HBox",
        ]

        picker = await W.ComboBox(dropdown_limit=10)
        for name in widget_names:
            await picker.append_text(name)
        await picker.set_index(0)
        await picker_content.add_widget(picker, 0)

        go_btn = await W.Button("Go!")
        await picker_content.add_widget(go_btn, 0)
        await picker_content.add_widget(await W.Label(""), 1)

        await mdi.add_widget(picker_content,
                             {"title": "Widget Picker", "width": 220,
                              "height": 180})

        # -- Demo creation --
        demo_count = 0

        def next_position():
            nonlocal demo_count
            demo_count += 1
            return (40 + (demo_count % 6) * 25, 20 + (demo_count % 6) * 25)

        async def make_demo(name):
            pos = next_position()

            if name == "Button":
                content = await W.VBox(spacing=6, padding=8)
                hbox = await W.HBox(spacing=6)
                lbl = await W.Label("")
                btn_a = await W.Button("Button A")
                async def on_a():
                    await lbl.set_text("Button A clicked")
                await btn_a.on("activated", on_a)
                btn_b = await W.Button("Button B")
                async def on_b():
                    await lbl.set_text("Button B clicked")
                await btn_b.on("activated", on_b)
                await hbox.add_widget(btn_a, 0)
                await hbox.add_widget(btn_b, 0)
                await content.add_widget(hbox, 0)
                await content.add_widget(lbl, 1)
                await mdi.add_widget(content,
                    {"title": "Button", "width": 300, "height": 120,
                     "x": pos[0], "y": pos[1]})

            elif name == "CheckBox":
                content = await W.VBox(spacing=4, padding=8)
                lbl = await W.Label("")
                cb1 = await W.CheckBox("Option 1")
                async def on_cb1(val):
                    await lbl.set_text(
                        f"Option 1: {'ON' if val else 'OFF'}")
                await cb1.on("activated", on_cb1)
                cb2 = await W.CheckBox("Option 2")
                async def on_cb2(val):
                    await lbl.set_text(
                        f"Option 2: {'ON' if val else 'OFF'}")
                await cb2.on("activated", on_cb2)
                cb3 = await W.CheckBox("Option 3")
                async def on_cb3(val):
                    await lbl.set_text(
                        f"Option 3: {'ON' if val else 'OFF'}")
                await cb3.on("activated", on_cb3)
                await content.add_widget(cb1, 0)
                await content.add_widget(cb2, 0)
                await content.add_widget(cb3, 0)
                await content.add_widget(lbl, 1)
                await mdi.add_widget(content,
                    {"title": "CheckBox", "width": 250, "height": 160,
                     "x": pos[0], "y": pos[1]})

            elif name == "ComboBox":
                content = await W.VBox(spacing=6, padding=8)
                lbl = await W.Label("")
                await content.add_widget(await W.Label("Pick-only:"), 0)
                combo1 = await W.ComboBox()
                for f in ["Apple", "Banana", "Cherry", "Date",
                           "Elderberry"]:
                    await combo1.append_text(f)
                await combo1.set_index(0)
                async def on_combo1(idx, text):
                    await lbl.set_text(f"Picked: {text}")
                await combo1.on("activated", on_combo1)
                await content.add_widget(combo1, 0)
                await content.add_widget(await W.Label("Editable:"), 0)
                combo2 = await W.ComboBox(editable=True, dropdown_limit=5)
                for c in ["Red", "Orange", "Yellow", "Green", "Blue",
                           "Indigo", "Violet"]:
                    await combo2.append_text(c)
                async def on_combo2(idx, text):
                    await lbl.set_text(f"Entered: {text}")
                await combo2.on("activated", on_combo2)
                await content.add_widget(combo2, 0)
                await content.add_widget(lbl, 1)
                await mdi.add_widget(content,
                    {"title": "ComboBox", "width": 280, "height": 200,
                     "x": pos[0], "y": pos[1]})

            elif name == "Dial":
                content = await W.HBox(spacing=8, padding=8)
                lbl = await W.Label("50")
                dial1 = await W.Dial(min=0, max=100, value=50, track=True)
                async def on_dial(val):
                    await lbl.set_text(str(val))
                await dial1.on("activated", on_dial)
                dial2 = await W.Dial(min=0, max=100, value=25)
                await dial2.on("activated", on_dial)
                await content.add_widget(dial1, 0)
                await content.add_widget(dial2, 0)
                await content.add_widget(lbl, 1)
                await mdi.add_widget(content,
                    {"title": "Dial", "width": 320, "height": 160,
                     "x": pos[0], "y": pos[1]})

            elif name == "Expander":
                content = await W.VBox(spacing=4, padding=8)
                exp1 = await W.Expander(title="Section A", collapsible=True)
                await exp1.set_widget(await W.Label("Content of section A."))
                exp2 = await W.Expander(title="Section B", collapsible=True)
                await exp2.set_widget(await W.Label("Content of section B."))
                await content.add_widget(exp1, 0)
                await content.add_widget(exp2, 0)
                await content.add_widget(await W.Label(""), 1)
                await mdi.add_widget(content,
                    {"title": "Expander", "width": 280, "height": 180,
                     "x": pos[0], "y": pos[1]})

            elif name == "Frame":
                content = await W.VBox(spacing=6, padding=8)
                frame1 = await W.Frame(title="Titled Frame")
                await frame1.set_widget(
                    await W.Label("Content inside a frame."))
                frame2 = await W.Frame(title="Another Frame")
                await frame2.set_widget(
                    await W.Label("More framed content."))
                await content.add_widget(frame1, 1)
                await content.add_widget(frame2, 1)
                await mdi.add_widget(content,
                    {"title": "Frame", "width": 280, "height": 200,
                     "x": pos[0], "y": pos[1]})

            elif name == "GridBox":
                content = await W.VBox(padding=8, spacing=6)
                lbl = await W.Label("")
                grid = await W.GridBox(rows=3, columns=3)
                for r in range(3):
                    for c in range(3):
                        btn = await W.Button(f"({r},{c})")
                        async def on_grid(_r=r, _c=c):
                            await lbl.set_text(
                                f"Clicked row={_r} col={_c}")
                        await btn.on("activated", on_grid)
                        await grid.add_widget(btn, r, c)
                await content.add_widget(grid, 1)
                await content.add_widget(lbl, 0)
                await mdi.add_widget(content,
                    {"title": "GridBox", "width": 280, "height": 200,
                     "x": pos[0], "y": pos[1]})

            elif name == "Label":
                content = await W.VBox(spacing=6, padding=8)
                lbl1 = await W.Label("Default label")
                lbl2 = await W.Label("Centered, colored")
                await lbl2.set_halign("center")
                await lbl2.set_color("#eef", "darkblue")
                lbl3 = await W.Label("Monospace, bold")
                await lbl3.set_font("monospace", 12, "bold")
                await content.add_widget(lbl1, 0)
                await content.add_widget(lbl2, 0)
                await content.add_widget(lbl3, 0)
                await content.add_widget(await W.Label(""), 1)
                await mdi.add_widget(content,
                    {"title": "Label", "width": 260, "height": 150,
                     "x": pos[0], "y": pos[1]})

            elif name == "ProgressBar":
                content = await W.VBox(spacing=6, padding=8)
                pb = await W.ProgressBar()
                await pb.set_value(0.65)
                slider = await W.Slider(min=0, max=100, value=65,
                                        track=True)
                async def on_pb_slider(val):
                    await pb.set_value(val / 100)
                await slider.on("activated", on_pb_slider)
                await content.add_widget(
                    await W.Label("Drag slider to change:"), 0)
                await content.add_widget(slider, 0)
                await content.add_widget(pb, 0)
                await content.add_widget(await W.Label(""), 1)
                await mdi.add_widget(content,
                    {"title": "ProgressBar", "width": 320, "height": 150,
                     "x": pos[0], "y": pos[1]})

            elif name == "RadioButton":
                content = await W.VBox(spacing=4, padding=8)
                lbl = await W.Label("")
                rb1 = await W.RadioButton("Choice A")
                async def on_rb1(val):
                    if val:
                        await lbl.set_text("Selected: A")
                await rb1.on("activated", on_rb1)
                rb2 = await W.RadioButton("Choice B", group=rb1)
                async def on_rb2(val):
                    if val:
                        await lbl.set_text("Selected: B")
                await rb2.on("activated", on_rb2)
                rb3 = await W.RadioButton("Choice C", group=rb1)
                async def on_rb3(val):
                    if val:
                        await lbl.set_text("Selected: C")
                await rb3.on("activated", on_rb3)
                await rb1.set_state(True)
                await content.add_widget(rb1, 0)
                await content.add_widget(rb2, 0)
                await content.add_widget(rb3, 0)
                await content.add_widget(lbl, 1)
                await mdi.add_widget(content,
                    {"title": "RadioButton", "width": 250, "height": 160,
                     "x": pos[0], "y": pos[1]})

            elif name == "ScrollArea":
                big = await W.VBox(spacing=4, padding=8)
                for i in range(30):
                    row = await W.HBox(spacing=4)
                    for j in range(8):
                        lbl = await W.Label(f"Item {i * 8 + j}")
                        await lbl.set_padding([2, 6, 2, 6])
                        await lbl.set_color(
                            "#f8f8f8" if i % 2 == 0 else "#fff", "#333")
                        await row.add_widget(lbl, 0)
                    await big.add_widget(row, 0)
                scroll = await W.ScrollArea()
                await scroll.set_widget(big)
                await mdi.add_widget(scroll,
                    {"title": "ScrollArea", "width": 320, "height": 200,
                     "x": pos[0], "y": pos[1]})

            elif name == "ScrollBar":
                content = await W.VBox(spacing=8, padding=8)
                lbl = await W.Label("0%")
                await content.add_widget(
                    await W.Label("Horizontal:"), 0)
                hsb = await W.ScrollBar(orientation="horizontal")
                await hsb.set_thumb_percent(0.2)
                async def on_hsb(pct):
                    await lbl.set_text(f"{int(pct * 100)}%")
                await hsb.on("activated", on_hsb)
                await content.add_widget(hsb, 0)
                hbox = await W.HBox(spacing=8)
                await hbox.add_widget(await W.Label("Vertical:"), 0)
                vsb = await W.ScrollBar(orientation="vertical")
                await vsb.set_thumb_percent(0.3)
                await vsb.on("activated", on_hsb)
                await hbox.add_widget(vsb, 0)
                await hbox.add_widget(lbl, 1)
                await content.add_widget(hbox, 1)
                await mdi.add_widget(content,
                    {"title": "ScrollBar", "width": 280, "height": 200,
                     "x": pos[0], "y": pos[1]})

            elif name == "Slider":
                content = await W.VBox(spacing=6, padding=8)
                lbl = await W.Label("")
                sl1 = await W.Slider(min=0, max=100, value=50)
                async def on_sl1(val):
                    await lbl.set_text(f"Integer: {val}")
                await sl1.on("activated", on_sl1)
                sl2 = await W.Slider(min=0, max=1, step=0.01, value=0.5,
                                     dtype="float", track=True)
                async def on_sl2(val):
                    await lbl.set_text(f"Float: {val}")
                await sl2.on("activated", on_sl2)
                await content.add_widget(
                    await W.Label("Integer (0-100):"), 0)
                await content.add_widget(sl1, 0)
                await content.add_widget(
                    await W.Label("Float tracking (0-1):"), 0)
                await content.add_widget(sl2, 0)
                await content.add_widget(lbl, 1)
                await mdi.add_widget(content,
                    {"title": "Slider", "width": 320, "height": 180,
                     "x": pos[0], "y": pos[1]})

            elif name == "SpinBox":
                content = await W.VBox(spacing=6, padding=8)
                lbl = await W.Label("")
                await content.add_widget(
                    await W.Label("Integer (0-100):"), 0)
                sp1 = await W.SpinBox(min=0, max=100, step=1, value=50)
                async def on_sp1(val):
                    await lbl.set_text(f"Int: {val}")
                await sp1.on("activated", on_sp1)
                await content.add_widget(sp1, 0)
                await content.add_widget(
                    await W.Label("Float (0-1):"), 0)
                sp2 = await W.SpinBox(min=0, max=1, step=0.05, value=0.5,
                                      dtype="float")
                async def on_sp2(val):
                    await lbl.set_text(f"Float: {val}")
                await sp2.on("activated", on_sp2)
                await content.add_widget(sp2, 0)
                await content.add_widget(lbl, 1)
                await mdi.add_widget(content,
                    {"title": "SpinBox", "width": 280, "height": 180,
                     "x": pos[0], "y": pos[1]})

            elif name == "Splitter":
                content = await W.VBox(padding=2, spacing=4)
                lbl = await W.Label(
                    "Drag the handles to resize panes.")
                hsplit = await W.Splitter(orientation="horizontal")
                p1 = await W.Label("Left")
                await p1.set_halign("center")
                await p1.set_color("#e8f0fe", "#333")
                p2 = await W.Label("Center")
                await p2.set_halign("center")
                await p2.set_color("#fef7e0", "#333")
                p3 = await W.Label("Right")
                await p3.set_halign("center")
                await p3.set_color("#e8fee8", "#333")
                await hsplit.add_widget(p1)
                await hsplit.add_widget(p2)
                await hsplit.add_widget(p3)
                await content.add_widget(hsplit, 1)
                await content.add_widget(lbl, 0)
                await mdi.add_widget(content,
                    {"title": "Splitter", "width": 360, "height": 180,
                     "x": pos[0], "y": pos[1]})

            elif name == "StackWidget":
                content = await W.VBox(spacing=6, padding=8)
                lbl = await W.Label("Page 1 visible")
                stack = await W.StackWidget()
                pages = []
                colors = ["#e8f0fe", "#fef7e0", "#e8fee8"]
                for n in range(1, 4):
                    pg = await W.VBox(padding=8)
                    pg_lbl = await W.Label(f"Stack page {n}")
                    await pg_lbl.set_color(colors[n - 1], "#333")
                    await pg_lbl.set_halign("center")
                    await pg.add_widget(pg_lbl, 1)
                    await stack.add_widget(pg, {"title": f"Page {n}"})
                    pages.append((pg, f"Page {n}"))
                btn_row = await W.HBox(spacing=4)
                for pg, nm in pages:
                    btn = await W.Button(nm)
                    async def on_page(_pg=pg, _nm=nm):
                        await stack.show_widget(_pg)
                        await lbl.set_text(f"{_nm} visible")
                    await btn.on("activated", on_page)
                    await btn_row.add_widget(btn, 0)
                await content.add_widget(btn_row, 0)
                await content.add_widget(stack, 1)
                await content.add_widget(lbl, 0)
                await mdi.add_widget(content,
                    {"title": "StackWidget", "width": 300, "height": 200,
                     "x": pos[0], "y": pos[1]})

            elif name == "TabWidget":
                content = await W.VBox(spacing=6, padding=8)
                lbl = await W.Label("")
                tabs = await W.TabWidget(closable=True, reorderable=True)
                colors = ["#e8f0fe", "#fef7e0", "#e8fee8"]
                for n in range(1, 4):
                    pg = await W.VBox(padding=8)
                    pg_lbl = await W.Label(f"Content of tab {n}")
                    await pg_lbl.set_halign("center")
                    await pg_lbl.set_color(colors[n - 1], "#333")
                    await pg.add_widget(pg_lbl, 1)
                    await tabs.add_widget(pg, {"title": f"Tab {n}"})
                async def on_page_switch(child, idx):
                    await lbl.set_text(f"Switched to tab {idx}")
                await tabs.on("page-switch", on_page_switch)
                add_btn = await W.Button("Add Tab")
                tab_counter = [3]
                async def on_add_tab():
                    tab_counter[0] += 1
                    n = tab_counter[0]
                    pg = await W.VBox(padding=8)
                    pg_lbl = await W.Label(f"Content of tab {n}")
                    await pg_lbl.set_halign("center")
                    await pg.add_widget(pg_lbl, 1)
                    await tabs.add_widget(pg, {"title": f"Tab {n}"})
                    await lbl.set_text(f"Added tab {n}")
                await add_btn.on("activated", on_add_tab)
                await content.add_widget(tabs, 1)
                btn_row = await W.HBox(spacing=6)
                await btn_row.add_widget(add_btn, 0)
                await btn_row.add_widget(lbl, 1)
                await content.add_widget(btn_row, 0)
                await mdi.add_widget(content,
                    {"title": "TabWidget", "width": 350, "height": 220,
                     "x": pos[0], "y": pos[1]})

            elif name == "TableView":
                content = await W.VBox(spacing=4, padding=4)
                lbl = await W.Label("")
                table = await W.TableView(
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
                await table.set_data([
                    {"NAME": "Alice", "DEPT": "Engineering",
                     "SALARY": 95000},
                    {"NAME": "Bob",   "DEPT": "Marketing",
                     "SALARY": 72000},
                    {"NAME": "Carol", "DEPT": "Engineering",
                     "SALARY": 102000},
                    {"NAME": "Dave",  "DEPT": "Sales",
                     "SALARY": 68000},
                    {"NAME": "Eve",   "DEPT": "Engineering",
                     "SALARY": 98000},
                    {"NAME": "Frank", "DEPT": "Marketing",
                     "SALARY": 75000},
                    {"NAME": "Grace", "DEPT": "Sales",
                     "SALARY": 71000},
                    {"NAME": "Heidi", "DEPT": "Engineering",
                     "SALARY": 110000},
                ])
                async def on_table_sel(items):
                    if len(items) == 1:
                        await lbl.set_text(
                            f"Selected: "
                            f"{items[0]['values'].get('NAME', '')}")
                    else:
                        await lbl.set_text(
                            f"Selected: {len(items)} rows")
                await table.on("selected", on_table_sel)
                async def on_table_act(values, path):
                    await lbl.set_text(
                        f"Activated: {values.get('NAME', '')}")
                await table.on("activated", on_table_act)
                hbox = await W.HBox(spacing=4)
                btn_add = await W.Button("Add Row")
                row_counter = [8]
                async def on_add_row():
                    row_counter[0] += 1
                    await table.append_row({
                        "NAME": f"Person {row_counter[0]}",
                        "DEPT": "New", "SALARY": 60000,
                    })
                await btn_add.on("activated", on_add_row)
                btn_sort = await W.Button("Sort by Name")
                async def on_sort():
                    await table.sort_by_column("NAME")
                await btn_sort.on("activated", on_sort)
                await hbox.add_widget(btn_add, 0)
                await hbox.add_widget(btn_sort, 0)
                await hbox.add_widget(lbl, 1)
                await content.add_widget(hbox, 0)
                await content.add_widget(table, 1)
                await mdi.add_widget(content,
                    {"title": "TableView", "width": 420, "height": 280,
                     "x": pos[0], "y": pos[1]})

            elif name == "TextArea":
                ta = await W.TextArea(
                    "This is a multi-line text area.\n\n"
                    "Edit this text freely.")
                await mdi.add_widget(ta,
                    {"title": "TextArea", "width": 320, "height": 200,
                     "x": pos[0], "y": pos[1]})

            elif name == "TextEntry":
                content = await W.VBox(spacing=6, padding=8)
                lbl = await W.Label("Press Enter to activate.")
                entry = await W.TextEntry(text="Type here",
                                          linehistory=10)
                async def on_entry(text):
                    await lbl.set_text(f"Entered: {text}")
                await entry.on("activated", on_entry)
                await content.add_widget(entry, 0)
                await content.add_widget(
                    await W.Label("Password:"), 0)
                pw = await W.TextEntry(password=True)
                async def on_pw(text):
                    await lbl.set_text(f"Password: {text}")
                await pw.on("activated", on_pw)
                await content.add_widget(pw, 0)
                await content.add_widget(lbl, 1)
                await mdi.add_widget(content,
                    {"title": "TextEntry", "width": 300, "height": 160,
                     "x": pos[0], "y": pos[1]})

            elif name == "TextEntrySet":
                content = await W.VBox(spacing=6, padding=8)
                lbl = await W.Label("Press Enter or click Set.")
                tes = await W.TextEntrySet(text="Set", value="Hello",
                                           linehistory=5)
                async def on_tes(text):
                    await lbl.set_text(f"Value: {text}")
                await tes.on("activated", on_tes)
                await content.add_widget(tes, 0)
                await content.add_widget(lbl, 1)
                await mdi.add_widget(content,
                    {"title": "TextEntrySet", "width": 300, "height": 120,
                     "x": pos[0], "y": pos[1]})

            elif name == "ToggleButton":
                content = await W.VBox(spacing=6, padding=8)
                lbl = await W.Label("")
                await content.add_widget(
                    await W.Label("Independent toggles:"), 0)
                hbox1 = await W.HBox(spacing=4)
                tb1 = await W.ToggleButton("Bold")
                async def on_tb1(st):
                    await lbl.set_text(
                        f"Bold: {'on' if st else 'off'}")
                await tb1.on("activated", on_tb1)
                tb2 = await W.ToggleButton("Italic")
                async def on_tb2(st):
                    await lbl.set_text(
                        f"Italic: {'on' if st else 'off'}")
                await tb2.on("activated", on_tb2)
                await hbox1.add_widget(tb1, 0)
                await hbox1.add_widget(tb2, 0)
                await content.add_widget(hbox1, 0)
                await content.add_widget(
                    await W.Label("Grouped (exclusive):"), 0)
                hbox2 = await W.HBox(spacing=4)
                tg1 = await W.ToggleButton("Left")
                tg2 = await W.ToggleButton("Center", group=tg1)
                tg3 = await W.ToggleButton("Right", group=tg1)
                async def on_tg1(st):
                    if st:
                        await lbl.set_text("Align: Left")
                await tg1.on("activated", on_tg1)
                async def on_tg2(st):
                    if st:
                        await lbl.set_text("Align: Center")
                await tg2.on("activated", on_tg2)
                async def on_tg3(st):
                    if st:
                        await lbl.set_text("Align: Right")
                await tg3.on("activated", on_tg3)
                await hbox2.add_widget(tg1, 0)
                await hbox2.add_widget(tg2, 0)
                await hbox2.add_widget(tg3, 0)
                await content.add_widget(hbox2, 0)
                await content.add_widget(lbl, 1)
                await mdi.add_widget(content,
                    {"title": "ToggleButton", "width": 300, "height": 180,
                     "x": pos[0], "y": pos[1]})

            elif name == "ToolBar":
                content = await W.VBox()
                lbl = await W.Label("Click toolbar items.")
                await lbl.set_padding(8)
                tb = await W.ToolBar()
                act1 = await tb.add_action({"text": "New"})
                async def on_new():
                    await lbl.set_text("New clicked")
                await act1.on("activated", on_new)
                act2 = await tb.add_action({"text": "Open"})
                async def on_open():
                    await lbl.set_text("Open clicked")
                await act2.on("activated", on_open)
                act3 = await tb.add_action({"text": "Save"})
                async def on_save():
                    await lbl.set_text("Save clicked")
                await act3.on("activated", on_save)
                await tb.add_separator()
                tog1 = await tb.add_action(
                    {"text": "B", "toggle": True})
                async def on_bold(st):
                    await lbl.set_text(
                        f"Bold: {'on' if st else 'off'}")
                await tog1.on("activated", on_bold)
                tog2 = await tb.add_action(
                    {"text": "I", "toggle": True})
                async def on_italic(st):
                    await lbl.set_text(
                        f"Italic: {'on' if st else 'off'}")
                await tog2.on("activated", on_italic)
                await content.add_widget(tb, 0)
                await content.add_widget(lbl, 1)
                await mdi.add_widget(content,
                    {"title": "ToolBar", "width": 350, "height": 120,
                     "x": pos[0], "y": pos[1]})

            elif name == "TreeView":
                content = await W.VBox(spacing=4, padding=4)
                lbl = await W.Label("")
                tree = await W.TreeView(
                    columns=[
                        {"label": "Name", "key": "NAME",
                         "type": "string"},
                        {"label": "Type", "key": "TYPE",
                         "type": "string"},
                        {"label": "Size (KB)", "key": "SIZE",
                         "type": "integer"},
                    ],
                    selection_mode="multiple",
                    alternate_row_colors=True,
                    sortable=True,
                )
                await tree.set_tree({
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
                async def on_tree_sel(items):
                    if len(items) == 1:
                        await lbl.set_text(
                            f"Selected: {items[0]['path']}")
                    else:
                        await lbl.set_text(
                            f"Selected: {len(items)} items")
                await tree.on("selected", on_tree_sel)
                async def on_tree_act(values, path):
                    await lbl.set_text(f"Activated: {path}")
                await tree.on("activated", on_tree_act)
                hbox = await W.HBox(spacing=4)
                btn_exp = await W.Button("Expand All")
                async def on_exp():
                    await tree.expand_all()
                await btn_exp.on("activated", on_exp)
                btn_col = await W.Button("Collapse All")
                async def on_col():
                    await tree.collapse_all()
                await btn_col.on("activated", on_col)
                await hbox.add_widget(btn_exp, 0)
                await hbox.add_widget(btn_col, 0)
                await hbox.add_widget(lbl, 1)
                await content.add_widget(hbox, 0)
                await content.add_widget(tree, 1)
                await mdi.add_widget(content,
                    {"title": "TreeView", "width": 420, "height": 300,
                     "x": pos[0], "y": pos[1]})

            elif name == "VBox/HBox":
                content = await W.VBox(spacing=6, padding=8)
                lbl = await W.Label(
                    "stretch=0 fixed, stretch=1 fills")
                hbox = await W.HBox(spacing=4)
                fixed1 = await W.Button("Fixed (0)")
                stretch1 = await W.Label("Stretch (1)")
                await stretch1.set_color("#e8f0fe", "#333")
                await stretch1.set_halign("center")
                fixed2 = await W.Button("Fixed (0)")
                await hbox.add_widget(fixed1, 0)
                await hbox.add_widget(stretch1, 1)
                await hbox.add_widget(fixed2, 0)
                await content.add_widget(
                    await W.Label("HBox - horizontal:"), 0)
                await content.add_widget(hbox, 0)
                inner = await W.VBox(spacing=4)
                top_l = await W.Label("Top (stretch=0)")
                await top_l.set_color("#fef7e0", "#333")
                await top_l.set_halign("center")
                mid_l = await W.Label("Middle (stretch=1)")
                await mid_l.set_color("#e8fee8", "#333")
                await mid_l.set_halign("center")
                bot_l = await W.Label("Bottom (stretch=0)")
                await bot_l.set_color("#fee8e8", "#333")
                await bot_l.set_halign("center")
                await inner.add_widget(top_l, 0)
                await inner.add_widget(mid_l, 1)
                await inner.add_widget(bot_l, 0)
                await content.add_widget(
                    await W.Label("VBox - vertical:"), 0)
                await content.add_widget(inner, 1)
                await content.add_widget(lbl, 0)
                await mdi.add_widget(content,
                    {"title": "VBox / HBox", "width": 360, "height": 280,
                     "x": pos[0], "y": pos[1]})

            else:
                return

            await status.set_text(f"Opened demo: {name}")

        async def on_go():
            idx = picker.get_index()
            if idx is not None and 0 <= idx < len(widget_names):
                await make_demo(widget_names[idx])

        await go_btn.on("activated", on_go)

        await top.set_widget(vbox)
        await top.show()

        print(f"Session {session.id}: all_widgets UI built.")

    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
