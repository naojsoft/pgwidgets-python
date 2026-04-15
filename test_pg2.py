"""Quick manual test for reconnection / reconstruction."""

import logging
import traceback

from pgwidgets.sync.application import Application

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pgwidgets")

app = Application(max_sessions=4, logger=logger)


@app.on_connect
def setup(session):
    try:
        print("on_connect called!", flush=True)
        W = session.get_widgets()
        top = W.TopLevel(title="Reconnect Test", resizable=True)
        top.resize(400, 300)
        print("TopLevel created", flush=True)
        vbox = W.VBox(spacing=8, padding=10)
        top.set_widget(vbox)
        label = W.Label("Counter: 0")
        btn = W.Button("Increment")
        vbox.add_widget(label, 0)
        vbox.add_widget(btn, 0)
        print("Widgets created", flush=True)

        count = [0]

        def on_click():
            count[0] += 1
            label.set_text(f"Counter: {count[0]}")

        btn.on("activated", on_click)

        top.show()
        print("show() done", flush=True)
    except Exception as e:
        print(f"ERROR in on_connect: {e}", flush=True)
        traceback.print_exc()


app.run()
