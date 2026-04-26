pgwidgets-python
================

Python bindings for the `pgwidgets <https://github.com/naojsoft/pgwidgets-js>`_
JavaScript widget library. Build desktop-style browser UIs from Python with a
familiar Qt/GTK-style API.

.. code-block:: python

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

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   getting-started
   architecture
   sync
   async
   web-servers
   widgets
   subclassing
   callbacks
   utilities
   extras

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/index
