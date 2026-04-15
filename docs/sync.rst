Synchronous API
===============

The sync API lives in ``pgwidgets.sync``. Widget constructors and method
calls block until the browser responds.

.. code-block:: python

   from pgwidgets.sync import Application

Application
-----------

.. code-block:: python

   app = Application(
       ws_port=9500,           # WebSocket port
       http_port=9501,         # HTTP server port
       host="127.0.0.1",      # bind address
       http_server=True,       # serve JS/CSS assets
       concurrency_handling="per_session",  # callback threading model
       max_sessions=1,         # max concurrent sessions (None=unlimited)
       logger=None,            # logging.Logger or None
   )

**Properties:**

- ``app.url`` -- URL to open in a browser (e.g. ``http://127.0.0.1:9501/``).
- ``app.sessions`` -- dict of active sessions (``session_id -> Session``).
- ``app.static_path`` -- path to the pgwidgets static files directory.
- ``app.remote_html`` -- path to the ``remote.html`` connector page.

**Methods:**

- ``app.create_session(session_id=None)`` -- create a session without a
  browser. Returns a ``Session`` that can have its widget tree built before
  any browser connects.

on_connect / on_disconnect
~~~~~~~~~~~~~~~~~~~~~~~~~~

Register handlers as decorators or by calling directly.

``on_connect`` fires when a **new** session is created (not on reconnection).
``on_disconnect`` fires each time a browser disconnects.

.. code-block:: python

   @app.on_connect
   def setup(session):
       Widgets = session.get_widgets()
       top = Widgets.TopLevel(title="Hello")
       top.show()

   @app.on_disconnect
   def teardown(session):
       print(f"Session {session.id}: browser disconnected "
             f"({len(session.connections)} remaining)")

Running
~~~~~~~

.. code-block:: python

   # Option 1: run() calls start() automatically and blocks forever
   app.run()

   # Option 2: start() + your own main loop
   app.start()
   # ... do other things ...

``app.close()`` shuts down all sessions and stops the servers.

Session
-------

Sessions persist independently of browser connections. A session can exist
with no browser connected and can have multiple browsers connected
simultaneously.

**Key methods:**

.. code-block:: python

   Widgets = session.get_widgets()   # widget factory namespace
   session.close()                   # close browser connections (session survives)
   session.destroy()                 # destroy session completely
   session.make_timer(duration=0)    # create a Timer widget

   # Schedule work on the callback thread
   session.gui_do(func, *args)       # fire-and-forget
   result = session.gui_call(func, *args)  # block for result

   # Widget tree inspection
   for widget in session.walk_widget_tree():
       print(widget)

**Properties:**

- ``session.id`` -- unique session identifier (int).
- ``session.app`` -- the owning ``Application``.
- ``session.token`` -- security token for reconnection.
- ``session.is_connected`` -- ``True`` if at least one browser is connected.
- ``session.connections`` -- list of active WebSocket connections.

Creating Sessions Without a Browser
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Use ``app.create_session()`` to create a session before any browser connects.
Build the widget tree, then connect a browser to see the pre-built UI:

.. code-block:: python

   app.start()
   session = app.create_session()
   Widgets = session.get_widgets()
   top = Widgets.TopLevel(title="Pre-built")
   top.show()
   # Navigate a browser to the session URL to see the UI.

Multi-Browser Support
~~~~~~~~~~~~~~~~~~~~~

Multiple browsers can connect to the same session by navigating to the
session URL (which includes the session ID and security token). All browsers
show the same UI and stay synchronized:

- State changes in one browser are pushed to all others in real time.
- Widget positions, slider values, tab selections, tree expand/collapse
  state, and more are all synchronized.
- Callbacks fire only in response to the originating browser's action;
  other browsers receive silent updates that don't trigger callbacks.

Widget Factory
~~~~~~~~~~~~~~

``session.get_widgets()`` returns a namespace with factory methods for all
widget types:

.. code-block:: python

   Widgets = session.get_widgets()

   top = Widgets.TopLevel(title="Demo", resizable=True)
   vbox = Widgets.VBox(spacing=8, padding=10)
   btn = Widgets.Button("Click me")
   label = Widgets.Label("Status", halign="center")
   slider = Widgets.Slider(min=0, max=100, value=50, track=True)

Constructor arguments match the widget definitions: positional args first,
then options as keyword arguments. Extra keyword arguments that do not match
a defined option are applied as ``set_<name>()`` calls.

Concurrency Modes
-----------------

The ``concurrency_handling`` parameter controls how widget callbacks are
dispatched:

**per_session** (default)
   Each session gets its own thread. Callbacks within a session are dispatched
   sequentially. Different sessions run concurrently. No locks needed within
   a session.

**serialized**
   All callbacks from all sessions run on the main thread inside ``run()``.
   Simple single-threaded model, but one slow callback blocks everything.

**concurrent**
   Each callback fires on its own daemon thread. Maximum concurrency, but
   you must manage thread safety for shared state.

gui_do and gui_call
~~~~~~~~~~~~~~~~~~~

In ``per_session`` and ``serialized`` modes, use ``gui_do`` and ``gui_call``
to schedule work on the callback thread from other threads:

.. code-block:: python

   import threading

   def background_work(session):
       # This runs on a background thread
       result = expensive_computation()
       # Schedule UI update on the callback thread
       session.gui_do(lambda: label.set_text(str(result)))

   threading.Thread(target=background_work, args=(session,)).start()

``gui_call`` blocks until the scheduled function completes and returns its
return value. ``gui_do`` returns immediately.

Full Example
------------

.. code-block:: python

   import logging
   from pgwidgets.sync import Application

   logging.basicConfig(level=logging.INFO)
   logger = logging.getLogger("pgwidgets")

   app = Application(max_sessions=4, logger=logger)

   @app.on_connect
   def on_session(session):
       Widgets = session.get_widgets()

       top = Widgets.TopLevel(title="Sync Demo", resizable=True)
       top.resize(400, 300)

       vbox = Widgets.VBox(spacing=8, padding=10)
       status = Widgets.Label("Click a button!")

       hbox = Widgets.HBox(spacing=6)
       btn_hello = Widgets.Button("Hello")
       btn_world = Widgets.Button("World")
       hbox.add_widget(btn_hello, 0)
       hbox.add_widget(btn_world, 0)

       entry = Widgets.TextEntry(text="Type here", linehistory=5)
       slider = Widgets.Slider(min=0, max=100, value=50, track=True)

       vbox.add_widget(hbox, 0)
       vbox.add_widget(entry, 0)
       vbox.add_widget(slider, 0)
       vbox.add_widget(status, 1)
       top.set_widget(vbox)
       top.show()

       btn_hello.on("activated", lambda: status.set_text("Hello!"))
       btn_world.on("activated", lambda: status.set_text("World!"))
       entry.on("activated", lambda text: status.set_text(f"Entered: {text}"))
       slider.on("activated", lambda val: status.set_text(f"Slider: {val}"))

   app.run()
