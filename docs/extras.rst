Extras
======

Higher-level composite widgets built from the core pgwidgets primitives.
These ship with pgwidgets but live in their own subpackage so the core
import surface stays minimal.

Import individual modules as needed::

    from pgwidgets.extras.file_browser import FileBrowser

FileBrowser
-----------

A file browser dialog assembled from a ``Dialog``, ``TableView``,
``TextEntry``, and ``ComboBox``.  All filesystem I/O happens on the
Python side.

Usage
~~~~~

.. code-block:: python

   from pgwidgets.sync import Application
   from pgwidgets.extras.file_browser import FileBrowser

   app = Application()

   @app.on_connect
   def setup(session):
       fb = FileBrowser(session, title="Open File", mode="file")
       fb.add_ext_filter("Images", "png")
       fb.add_ext_filter("Images", "jpg")
       fb.add_ext_filter("Images", "fits")
       fb.on("activated", lambda path: print(f"Selected: {path}"))
       fb.popup()

   app.run()

Constructor parameters
~~~~~~~~~~~~~~~~~~~~~~

``FileBrowser(session, title="Browse", modal=True, autoclose=True, mode="file")``

* ``session`` -- the pgwidgets ``Session``.
* ``title`` -- dialog title.
* ``modal`` -- whether the dialog is modal.
* ``autoclose`` -- whether the dialog closes after a selection is made.
* ``mode`` -- one of:

  * ``"file"`` -- pick a single existing file (default).
  * ``"files"`` -- pick multiple existing files.
  * ``"directory"`` -- pick a directory.
  * ``"save"`` -- pick a filename for saving (prompts on overwrite).

Methods
~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Method
     - Description
   * - ``set_directory(path)``
     - Set the starting directory.
   * - ``set_filename(name)``
     - Pre-fill the filename entry.
   * - ``set_mode(mode)``
     - Change the selection mode.
   * - ``add_ext_filter(category, ext)``
     - Add a file-extension filter (e.g.
       ``add_ext_filter("Images", "png")``).  Multiple extensions can
       be grouped under the same category by calling repeatedly.
   * - ``clear_filters()``
     - Remove all extension filters.
   * - ``popup(x=None, y=None)``
     - Show the file browser dialog.
   * - ``on("activated", callback)``
     - Register a callback fired with the selected path when the user
       confirms a selection.  In ``mode="files"`` the callback receives
       a list of paths.
