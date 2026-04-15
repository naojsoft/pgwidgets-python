Asynchronous API
================

The async API lives in ``pgwidgets.async_``. All widget constructors and
method calls are coroutines that must be awaited.

.. code-block:: python

   from pgwidgets.async_ import Application

Application
-----------

.. code-block:: python

   app = Application(
       ws_port=9500,
       http_port=9501,
       host="127.0.0.1",
       http_server=True,
       concurrency_handling="per_session",
       max_sessions=1,
       logger=None,
   )

The constructor parameters are the same as the sync version (see :doc:`sync`).

on_connect / on_disconnect
~~~~~~~~~~~~~~~~~~~~~~~~~~

Handlers can be sync or async:

.. code-block:: python

   @app.on_connect
   async def setup(session):
       Widgets = session.get_widgets()
       top = await Widgets.TopLevel(title="Hello")
       await top.show()

   @app.on_disconnect
   async def teardown(session):
       print(f"Session {session.id} disconnected")

Running
~~~~~~~

.. code-block:: python

   # Inside an async context
   await app.run()

   # Or with asyncio.run()
   import asyncio
   asyncio.run(main())

``await app.close()`` shuts down all sessions and causes ``run()`` to return.

Session
-------

The async ``Session`` has the same interface as the sync version, but most
methods are coroutines. Sessions persist independently of browser connections,
support reconnection and multi-browser synchronization (see :doc:`sync` for
details on these features).

.. code-block:: python

   Widgets = session.get_widgets()          # sync -- returns namespace
   btn = await Widgets.Button("Click me")   # async -- creates widget
   await btn.set_text("New text")           # async -- calls method
   text = btn.get_text()                    # sync -- returns from local state
   await session.close()                    # async
   timer = await session.make_timer(duration=1000)  # async

**Properties:**

- ``session.id`` -- unique session identifier.
- ``session.app`` -- the owning ``Application``.
- ``session.token`` -- security token for reconnection.
- ``session.is_connected`` -- ``True`` if at least one browser is connected.
- ``session.connections`` -- list of active WebSocket connections.

**Getter methods** (``get_text()``, ``get_value()``, ``is_visible()``, etc.)
return from local state without a browser round-trip and do **not** need to
be awaited. All other widget methods (setters, actions, child methods) are
coroutines and must be awaited.

Creating Sessions Without a Browser
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   session = app.create_session()
   # Build widgets -- sends are queued; no browser needed.
   # Connect a browser later to see the pre-built UI.

Concurrency Modes
-----------------

In the async API, concurrency is managed with ``asyncio.Lock`` instead of
threads:

**per_session** (default)
   Each session gets its own ``asyncio.Lock``. Callbacks within a session
   are serialized, but different sessions can interleave at ``await`` points.

**serialized**
   All callbacks from all sessions are serialized under a single global
   ``asyncio.Lock``.

**concurrent**
   Callbacks are dispatched via ``asyncio.ensure_future`` with no
   serialization.

Callbacks
~~~~~~~~~

Callback handlers can be sync or async. Async handlers are awaited:

.. code-block:: python

   async def on_click():
       await status.set_text("Clicked!")

   await btn.on("activated", on_click)

Full Example
------------

.. code-block:: python

   import asyncio
   import logging
   from pgwidgets.async_ import Application

   logging.basicConfig(level=logging.INFO)
   logger = logging.getLogger("pgwidgets")

   async def main():
       app = Application(max_sessions=4, logger=logger)

       @app.on_connect
       async def on_session(session):
           Widgets = session.get_widgets()

           top = await Widgets.TopLevel(title="Async Demo", resizable=True)
           await top.resize(400, 300)

           vbox = await Widgets.VBox(spacing=8, padding=10)
           status = await Widgets.Label("Click a button!")

           hbox = await Widgets.HBox(spacing=6)
           btn = await Widgets.Button("Hello")
           await hbox.add_widget(btn, 0)

           entry = await Widgets.TextEntry(text="Type here", linehistory=5)

           await vbox.add_widget(hbox, 0)
           await vbox.add_widget(entry, 0)
           await vbox.add_widget(status, 1)
           await top.set_widget(vbox)
           await top.show()

           async def on_hello():
               await status.set_text("Hello!")

           async def on_entry(text):
               await status.set_text(f"Entered: {text}")

           await btn.on("activated", on_hello)
           await entry.on("activated", on_entry)

       await app.run()

   if __name__ == "__main__":
       asyncio.run(main())
