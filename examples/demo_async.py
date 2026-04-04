#!/usr/bin/env python3
"""
Asynchronous pgwidgets demo.

Run this script and open the URL it prints in a browser.
"""

import asyncio
from pgwidgets.async_ import Application


async def main():
    app = Application()
    W = app.get_widgets()

    # Start servers in background, then build UI
    async def build_ui():
        print("Waiting for browser connection...")
        await app.wait_for_connection()
        print("Connected!")

        # Build the UI
        top = await W.TopLevel(title="Async Demo", resizable=True)
        await top.resize(400, 300)

        vbox = await W.VBox(spacing=8, padding=10)

        status = await W.Label("Click a button!")

        hbox = await W.HBox(spacing=6)
        btn_hello = await W.Button("Hello")
        btn_world = await W.Button("World")
        btn_clear = await W.Button("Clear")
        await hbox.add_widget(btn_hello, 0)
        await hbox.add_widget(btn_world, 0)
        await hbox.add_widget(btn_clear, 0)

        entry = await W.TextEntry(text="Type here", linehistory=5)
        slider = await W.Slider(min=0, max=100, value=50, track=True)

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

        print("UI built. Interact with the browser window.")

    asyncio.ensure_future(build_ui())
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())
