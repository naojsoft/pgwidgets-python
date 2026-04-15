Getting Started
===============

Installation
------------

.. code-block:: bash

   pip install pgwidgets-python

This installs ``pgwidgets-js`` (the JavaScript assets) and ``websockets`` as
dependencies.

For development (Sphinx docs, etc.):

.. code-block:: bash

   pip install pgwidgets-python[dev]

Quick Start
-----------

Create a file ``hello.py``:

.. code-block:: python

   from pgwidgets.sync import Application

   app = Application()

   @app.on_connect
   def setup(session):
       Widgets = session.get_widgets()

       top = Widgets.TopLevel(title="Hello", resizable=True)
       top.resize(400, 300)

       btn = Widgets.Button("Click me")
       label = Widgets.Label("Ready")

       btn.on("activated", lambda: label.set_text("Clicked!"))

       vbox = Widgets.VBox(spacing=8, padding=10)
       vbox.add_widget(btn, 0)
       vbox.add_widget(label, 1)
       top.set_widget(vbox)
       top.show()

   app.run()

Run it:

.. code-block:: bash

   python hello.py

Open the URL printed in the console (default ``http://127.0.0.1:9501/``)
in your browser.

Running the Examples
--------------------

The repository includes several demo scripts:

.. code-block:: bash

   # Synchronous demos
   python examples/demo_sync.py
   python examples/all_widgets.py

   # Asynchronous demos
   python examples/demo_async.py
   python examples/all_widgets_async.py

The ``all_widgets`` demos showcase every widget type in an MDI workspace.
Try refreshing the browser to see automatic UI reconstruction, or open
the session URL in a second browser tab to see multi-browser synchronization.

Choosing Sync vs Async
----------------------

Use **sync** (``pgwidgets.sync``) unless you are integrating with an existing
asyncio application. The sync API is simpler -- widget constructors and method
calls are blocking and return values directly:

.. code-block:: python

   btn = Widgets.Button("Click")
   btn.set_text("New text")

The **async** API (``pgwidgets.async_``) requires ``await`` on every widget
operation (except getters, which return from local state):

.. code-block:: python

   btn = await Widgets.Button("Click")
   await btn.set_text("New text")
   text = btn.get_text()  # sync -- no await needed

Both APIs provide identical widget classes, methods, session persistence,
reconnection, and multi-browser synchronization.
