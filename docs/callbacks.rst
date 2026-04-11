Callback System
===============

pgwidgets uses a callback model where the browser sends event messages to
Python over WebSocket. You register handlers in Python; they fire when the
user interacts with widgets in the browser.

Registering Callbacks
---------------------

There are two ways to register a callback on any widget:

**on()** -- handler receives only the callback arguments:

.. code-block:: python

   # Sync
   btn.on("activated", lambda: print("clicked"))
   entry.on("activated", lambda text: print(f"Entered: {text}"))

   # Async
   await btn.on("activated", on_click)

**add_callback()** -- handler receives the widget as the first argument:

.. code-block:: python

   # Sync
   btn.add_callback("activated", lambda widget: print(f"{widget} clicked"))

   # Async
   await btn.add_callback("activated", on_click)

Extra Arguments
~~~~~~~~~~~~~~~

Both ``on()`` and ``add_callback()`` accept extra positional and keyword
arguments that are appended to every invocation:

.. code-block:: python

   def on_button(label, tag):
       label.set_text(f"Button {tag} clicked")

   btn_a.on("activated", on_button, status_label, "A")
   btn_b.on("activated", on_button, status_label, "B")

Callback Signatures
-------------------

Different callbacks pass different arguments to the handler. Below are the
common patterns:

.. list-table::
   :widths: 25 35 40
   :header-rows: 1

   * - Callback
     - Widgets
     - Handler receives
   * - ``activated``
     - Button
     - (nothing)
   * - ``activated``
     - CheckBox
     - ``(state: bool)``
   * - ``activated``
     - TextEntry
     - ``(text: str)``
   * - ``activated``
     - Slider, SpinBox, Dial
     - ``(value: number)``
   * - ``activated``
     - ComboBox
     - ``(index: int)``
   * - ``activated``
     - Dialog
     - ``(button_text: str)``
   * - ``page-switch``
     - TabWidget, StackWidget
     - ``(index: int)``
   * - ``page-close``
     - TabWidget, MDIWidget
     - ``(index: int)``
   * - ``selected``
     - TreeView, TableView
     - ``(selected_items)``
   * - ``pointer-down``
     - Image, Canvas
     - ``(event: dict)``
   * - ``drop-end``
     - Image, Canvas, Label, ...
     - ``(payload: dict)``
   * - ``expired``
     - Timer
     - (nothing)

Async Callbacks
~~~~~~~~~~~~~~~

In the async API, callback handlers can be sync or async functions. Async
handlers are automatically awaited:

.. code-block:: python

   async def on_click():
       await status.set_text("Clicked!")

   await btn.on("activated", on_click)

File Transfers (Chunked Protocol)
---------------------------------

When a user drags and drops files onto a widget (e.g., Image or Canvas with
``drop-end``), the file data is transferred in chunks to avoid blocking the
WebSocket with large payloads.

The protocol works as follows:

1. The browser sends a ``callback`` message with ``transfer_id`` and file
   metadata (names, sizes, MIME types) but no file data.
2. The framework fires a **drop-start** callback with the metadata so you
   can show progress UI.
3. The browser sends ``file-chunk`` messages with base64-encoded data.
4. The framework fires **drop-progress** callbacks with transfer status.
5. When all chunks arrive, the framework reassembles the data and fires the
   **drop-end** callback with the complete payload.

drop-start
~~~~~~~~~~

Fires once at the beginning of a file transfer. The handler receives a dict
with file metadata:

.. code-block:: python

   def on_drop_start(payload):
       files = payload["files"]  # list of {name, size, type}
       print(f"Receiving {len(files)} files...")

   widget.on("drop-start", on_drop_start)

drop-progress
~~~~~~~~~~~~~

Fires after each chunk. The handler receives a dict:

.. code-block:: python

   def on_progress(info):
       pct = info["transferred_bytes"] / info["total_bytes"] * 100
       progress_bar.set_value(pct)
       if info["complete"]:
           print("Transfer complete!")

   widget.on("drop-progress", on_progress)

The progress dict contains:

- ``transfer_id`` -- unique ID for this transfer
- ``file_index`` -- which file (0-based)
- ``chunk_index`` -- which chunk of the current file
- ``num_chunks`` -- total chunks for the current file
- ``transferred_bytes`` -- bytes received so far (all files)
- ``total_bytes`` -- total bytes expected (all files)
- ``complete`` -- True when all files are fully received

drop-end
~~~~~~~~

Fires when all file data has been received. The handler receives the full
payload with base64 data URIs:

.. code-block:: python

   import base64

   def on_drop(payload):
       for f in payload["files"]:
           name = f["name"]
           size = f["size"]
           mime = f["type"]
           data_uri = f["data"]  # "data:<mime>;base64,<data>"

           # Decode the file content
           b64 = data_uri.split(",", 1)[1]
           content = base64.b64decode(b64)
           print(f"Received {name}: {len(content)} bytes")

   widget.on("drop-end", on_drop)

Example: File Drop Zone
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   drop_label = Widgets.Label("Drop files here")
   drop_label.set_color("#e8f0fe", "#4a86c8")
   textarea = Widgets.TextArea("")

   def on_drop_start(payload):
       n = len(payload["files"])
       drop_label.set_text(f"Receiving {n} file(s)...")

   def on_drop(payload):
       f = payload["files"][0]
       b64 = f["data"].split(",", 1)[1]
       text = base64.b64decode(b64).decode("utf-8", errors="replace")
       textarea.set_text(text)
       drop_label.set_text(f"Loaded: {f['name']}")

   drop_label.on("drop-start", on_drop_start)
   drop_label.on("drop-end", on_drop)
