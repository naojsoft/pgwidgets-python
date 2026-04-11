Getting Started
===============

Installation
------------

.. code-block:: bash

   pip install pgwidgets

This installs ``pgwidgets-js`` (the JavaScript assets) and ``websockets`` as
dependencies.

For development (Sphinx docs, etc.):

.. code-block:: bash

   pip install pgwidgets[dev]

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

The repository includes two demo scripts:

.. code-block:: bash

   # Synchronous demo
   python examples/demo_sync.py

   # Asynchronous demo
   python examples/demo_async.py

Both demos show buttons, text entry, sliders, and drag-and-drop.

Choosing Sync vs Async
----------------------

Use **sync** (``pgwidgets.sync``) unless you are integrating with an existing
asyncio application. The sync API is simpler -- widget constructors and method
calls are blocking and return values directly:

.. code-block:: python

   btn = Widgets.Button("Click")
   btn.set_text("New text")

The **async** API (``pgwidgets.async_``) requires ``await`` on every widget
operation:

.. code-block:: python

   btn = await Widgets.Button("Click")
   await btn.set_text("New text")

Both APIs provide identical widget classes and methods.
