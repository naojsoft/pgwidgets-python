#!/usr/bin/env python3
"""
Asynchronous pgwidgets demo.

Run this script and open the URL it prints in a browser.
"""

import asyncio
from pgwidgets.async_ import Application


async def main():
    app = Application(max_sessions=4)

    @app.on_connect
    async def on_session(session):
        Widgets = session.get_widgets()

        # Build the UI
        top = await Widgets.TopLevel(title="Async Demo", resizable=True)
        await top.resize(400, 300)

        vbox = await Widgets.VBox(spacing=8, padding=10)

        status = await Widgets.Label("Click a button!")

        hbox = await Widgets.HBox(spacing=6)
        btn_hello = await Widgets.Button("Hello")
        btn_world = await Widgets.Button("World")
        btn_clear = await Widgets.Button("Clear")
        await hbox.add_widget(btn_hello, 0)
        await hbox.add_widget(btn_world, 0)
        await hbox.add_widget(btn_clear, 0)

        entry = await Widgets.TextEntry(text="Type here", linehistory=5)
        slider = await Widgets.Slider(min=0, max=100, value=50, track=True)

        await vbox.add_widget(hbox, 0)
        await vbox.add_widget(entry, 0)
        await vbox.add_widget(slider, 0)
        await vbox.add_widget(status, 1)

        await top.set_widget(vbox)
        await top.show()

        # Wire up callbacks
        async def on_hello():
            await status.set_text("Hello!")

        async def on_world():
            await status.set_text("World!")

        async def on_clear():
            await status.set_text("")
            await entry.set_text("")

        async def on_entry(text):
            await status.set_text(f"Entered: {text}")

        async def on_slider(value):
            await status.set_text(f"Slider: {value}")

        await btn_hello.on("activated", on_hello)
        await btn_world.on("activated", on_world)
        await btn_clear.on("activated", on_clear)
        await entry.on("activated", on_entry)
        await slider.on("activated", on_slider)

        print(f"Session {session.id}: UI built.")

    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
