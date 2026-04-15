Subclassing Widgets
===================

pgwidgets generates widget classes from shared definitions. Each class has
a proper Python constructor with named parameters, so you can subclass them
using normal Python class syntax.

Widget Class Basics
-------------------

Every widget class has a constructor signature derived from the widget
definition. For example:

.. code-block:: python

   # Button has one positional arg "text"
   Button(session, text=None, **kwargs)

   # TopLevel has keyword-only options
   TopLevel(session, *, resizable=None, title=None, moveable=None,
            closeable=None, **kwargs)

   # Dialog has positional args and keyword-only options
   Dialog(session, title=None, buttons=None, *, autoclose=None,
          resizable=None, moveable=None, modal=None, **kwargs)

The first argument is always the ``session``. Positional args match the
widget definition's ``args`` list and default to ``None``. Options are
keyword-only and also default to ``None``. Extra keyword arguments are
applied as ``set_<name>()`` calls.

When using ``session.get_widgets()``, the session is bound automatically:

.. code-block:: python

   W = session.get_widgets()
   btn = W.Button("Click me")          # session is injected
   top = W.TopLevel(title="My App")    # same

Importing Widget Classes
------------------------

Widget classes can be imported directly from the ``Widgets`` module:

.. code-block:: python

   from pgwidgets.sync.Widgets import Button, Label, TopLevel, Widget
   from pgwidgets.async_.Widgets import Button, Label, TopLevel, Widget  # async

These are the same classes returned by ``build_all_widget_classes()`` and
used internally by ``session.get_widgets()``. They can be subclassed,
type-checked, and used with ``isinstance()``.

Subclassing with get_widgets()
------------------------------

The simplest way to subclass is through the namespace returned by
``session.get_widgets()``:

.. code-block:: python

   from pgwidgets.sync import Application

   app = Application()

   @app.on_connect
   def setup(session):
       W = session.get_widgets()

       class StatusButton(W.Button):
           """A button that updates a status label when clicked."""

           def __init__(self, text, status_label, **kwargs):
               super().__init__(session, text, **kwargs)
               self.status_label = status_label
               self.on("activated", self._on_click)

           def _on_click(self):
               self.status_label.set_text(f"{self.get_text()} clicked!")

       top = W.TopLevel(title="Custom Widgets", resizable=True)
       vbox = W.VBox(spacing=8, padding=10)
       status = W.Label("Ready")
       btn = StatusButton("Press me", status)

       vbox.add_widget(btn, 0)
       vbox.add_widget(status, 1)
       top.set_widget(vbox)
       top.show()

   app.run()

The subclass constructor calls ``super().__init__(session, text, **kwargs)``
which handles all the internal plumbing: allocating a widget ID, creating
the widget in the browser, registering state tracking, etc.

Subclassing with Module-Level Imports
-------------------------------------

For larger applications you may want widget subclasses defined in their
own modules. Import the base classes from ``pgwidgets.sync.Widgets`` (or
``pgwidgets.async_.Widgets``) and pass the session explicitly when
creating instances:

.. code-block:: python

   # my_widgets.py
   from pgwidgets.sync.Widgets import Button, VBox, Label

   class StatusButton(Button):
       """A button that updates a status label when clicked."""

       def __init__(self, session, text, status_label, **kwargs):
           super().__init__(session, text, **kwargs)
           self.status_label = status_label
           self.on("activated", self._on_click)

       def _on_click(self):
           self.status_label.set_text(f"{self.get_text()} clicked!")

   class StatusPanel(VBox):
       """A panel with a button and a status label."""

       def __init__(self, session, button_text="Go", **kwargs):
           super().__init__(session, **kwargs)
           self.status = Label(session, "Ready")
           self.btn = StatusButton(session, button_text, self.status)
           self.add_widget(self.btn, 0)
           self.add_widget(self.status, 1)

.. code-block:: python

   # app.py
   from pgwidgets.sync import Application
   from my_widgets import StatusPanel

   app = Application()

   @app.on_connect
   def setup(session):
       W = session.get_widgets()
       top = W.TopLevel(title="My App", resizable=True)
       panel = StatusPanel(session, "Click me", spacing=8, padding=10)
       top.set_widget(panel)
       top.show()

   app.run()

Note that ``spacing=8`` and ``padding=10`` are passed through ``**kwargs``
to VBox's constructor, where they are applied as ``set_spacing(8)`` and
``set_padding(10)``.

Async Subclassing
-----------------

The async API uses the same pattern, but widget construction is awaitable.
The base ``Widget.__init__`` is synchronous (it parses arguments and
stores state), while the actual browser-side creation happens in an
``_initialize()`` coroutine triggered by ``await``:

.. code-block:: python

   # my_async_widgets.py
   from pgwidgets.async_.Widgets import Button

   class StatusButton(Button):
       def __init__(self, session, text, status_label, **kwargs):
           self.status_label = status_label
           super().__init__(session, text, **kwargs)

       async def _initialize(self):
           result = await super()._initialize()
           await self.on("activated", self._on_click)
           return result

       async def _on_click(self):
           await self.status_label.set_text(f"{self.get_text()} clicked!")

.. code-block:: python

   # app.py
   @app.on_connect
   async def setup(session):
       W = session.get_widgets()
       status = await W.Label("Ready")
       btn = await StatusButton(session, "Press me", status)

The ``await`` on the constructor triggers ``_initialize()`` which calls
``super()._initialize()`` (creating the widget in the browser) and then
performs any additional async setup.

Constructor Parameters
----------------------

Each widget class has named parameters generated from the widget
definitions. You can inspect them:

.. code-block:: python

   import inspect
   from pgwidgets.sync.Widgets import Button, TopLevel, Slider

   print(inspect.signature(Button.__init__))
   # (self, session, text=None, **kwargs)

   print(inspect.signature(TopLevel.__init__))
   # (self, session, *, resizable=None, title=None, moveable=None,
   #  closeable=None, **kwargs)

   print(inspect.signature(Slider.__init__))
   # (self, session, *, orientation=None, track=None, dtype=None,
   #  min=None, max=None, step=None, value=None, show_value=None,
   #  **kwargs)

When subclassing, your ``__init__`` can add its own parameters and forward
the rest to ``super().__init__``:

.. code-block:: python

   class MySlider(Slider):
       def __init__(self, session, label_text="Value", **kwargs):
           # kwargs may include min=, max=, value=, etc.
           super().__init__(session, **kwargs)
           self._label_text = label_text

Internal Construction
---------------------

There are two paths for creating widget instances:

**Normal construction** (``Widget.__init__``):
   Allocates a widget ID, sends a ``create`` message to the browser,
   registers state tracking and auto-sync listeners, and adds the widget
   to the session's root widget list. This is what happens when you call
   ``Button(session, "text")`` or ``W.Button("text")``.

**Internal construction** (``Widget._from_existing()``):
   A classmethod that creates a Python wrapper for a widget that already
   exists on the browser side. Used internally during reconstruction
   (reconnection) and when the browser returns a new widget reference
   (e.g., ``MDISubWindow`` wrappers). Does not send any messages to the
   browser. Not intended for application code.
