# pgwidgets — Python Bindings

Python bindings for the [pgwidgets](https://github.com/naojsoft/pgwidgets-js)
JavaScript widget library. Build desktop-style browser UIs from Python
with a familiar Qt/GTK-style API.

## Documentation

Full documentation is available at
[pgwidgets-python.readthedocs.io](https://pgwidgets-python.readthedocs.io/en/latest/).

## Installation

```bash
pip install pgwidgets-python
```

This will also install `pgwidgets-js` (the JavaScript assets) and
`websockets` as dependencies.

## Quick Start

```python
from pgwidgets.sync import Application

app = Application()

@app.on_connect
def setup(session):
    Widgets = session.get_widgets()

    top = Widgets.TopLevel(title="Hello", resizable=True)
    top.resize(400, 300)

    vbox = Widgets.VBox(spacing=8, padding=10)
    btn = Widgets.Button("Click me")
    label = Widgets.Label("Ready")

    btn.on("activated", lambda: label.set_text("Clicked!"))

    vbox.add_widget(btn, 0)
    vbox.add_widget(label, 1)
    top.set_widget(vbox)
    top.show()

app.run()
```

Run the script, then open the printed URL in your browser.

## Sync vs Async

Both APIs provide the same widget classes and methods.

**Synchronous** (recommended for most use cases):
```python
from pgwidgets.sync import Application
app = Application()

@app.on_connect
def setup(session):
    Widgets = session.get_widgets()
    btn = Widgets.Button("Click")      # blocking call
    btn.set_text("New text")           # blocking call

app.run()
```

**Asynchronous** (for asyncio applications):
```python
from pgwidgets.async_ import Application
app = Application()

@app.on_connect
async def setup(session):
    Widgets = session.get_widgets()
    btn = await Widgets.Button("Click")    # awaitable
    await btn.set_text("New text")         # awaitable

await app.run()
```

## How It Works

The `Application` class starts two servers:
- An **HTTP server** (default port 9501) that serves the pgwidgets JS/CSS
  and a connector page
- A **WebSocket server** (default port 9500) for the JSON command protocol

When you open the URL in a browser, the page loads pgwidgets and connects
back over WebSocket. Python widget constructors and method calls are
translated to JSON messages and executed in the browser. Callbacks are
forwarded back to Python.

## License

BSD 3-Clause
