Extras
======

Higher-level composite widgets built from the core pgwidgets primitives.
These ship with pgwidgets but live in their own subpackage so the core
import surface stays minimal.

Import individual modules as needed::

    from pgwidgets.extras.file_browser import FileBrowser

FileBrowser
-----------

A file/folder selection dialog assembled from a ``Dialog``,
``TableView``, ``TextEntry``, and ``ComboBox``.  All filesystem I/O
runs on the Python side; the browser only renders the listing
returned by the server, so the dialog reads the *server's* filesystem
(this is by design — it lets you build server-side tools that browse
server-side data).

Quick start
~~~~~~~~~~~

.. code-block:: python

   from pgwidgets.sync import Application
   from pgwidgets.extras.file_browser import FileBrowser

   app = Application()

   @app.on_connect
   def setup(session):
       fb = FileBrowser(session, title="Open Image", mode="file")
       fb.add_ext_filter("Images", "png")
       fb.add_ext_filter("Images", "jpg")
       fb.add_ext_filter("Images", "fits")
       fb.set_directory("/data/images")
       fb.on("activated", lambda path: print(f"Selected: {path}"))
       fb.popup()

   app.run()

Constructor
~~~~~~~~~~~

.. code-block:: python

   FileBrowser(
       session,
       title="Browse",
       modal=True,
       autoclose=True,
       mode="file",
   )

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Parameter
     - Description
   * - ``session``
     - The pgwidgets ``Session`` instance.  Required.
   * - ``title``
     - Title shown in the dialog's title bar.
   * - ``modal``
     - When ``True`` (default), the dialog is modal and blocks
       interaction with widgets behind it.
   * - ``autoclose``
     - When ``True`` (default), the dialog hides itself automatically
       after the user confirms a selection.  Set to ``False`` if you
       want to keep the dialog open after the ``"activated"``
       callback fires.
   * - ``mode``
     - Selection mode.  See :ref:`fb-modes`.

.. _fb-modes:

Modes
~~~~~

.. list-table::
   :header-rows: 1
   :widths: 18 82

   * - Mode
     - Behavior
   * - ``"file"``
     - Pick a single existing file.  Confirm button shows "Open".
       Double-click on a file selects it.  ``"activated"`` fires with
       the absolute path as a string.
   * - ``"files"``
     - Pick multiple existing files via the table's multi-selection.
       Confirm button shows "Open".  ``"activated"`` fires with a
       list of absolute paths.
   * - ``"directory"``
     - Pick a directory.  Confirm button shows "Select".  Double-click
       navigates into the folder; the user must press the confirm
       button (or type a folder name and confirm) to select.
       ``"activated"`` fires with the directory path as a string.
   * - ``"save"``
     - Pick a filename for saving.  Confirm button shows "Save".  If
       the typed name matches an existing file, a confirmation dialog
       prompts to overwrite.  ``"activated"`` fires with the absolute
       path as a string only after the user confirms (or if the file
       does not exist).

Methods
~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Method
     - Description
   * - ``set_directory(path)``
     - Set the starting directory.  If not called, the dialog opens
       in the process's current working directory the first time
       ``popup()`` is called.
   * - ``set_filename(name)``
     - Pre-fill the filename entry — useful for ``"save"`` mode to
       suggest a default filename.
   * - ``set_mode(mode)``
     - Change the selection mode (``"file"``, ``"files"``,
       ``"directory"``, or ``"save"``).
   * - ``add_ext_filter(category, ext)``
     - Add a file-extension filter to the filter ComboBox at the
       bottom of the dialog.  Calling repeatedly with the same
       ``category`` groups extensions::

           fb.add_ext_filter("Images", "png")
           fb.add_ext_filter("Images", "jpg")
           # Filter combo shows: "Images (*.png, *.jpg)"

       Matching is case-insensitive on both the filter and the
       file extension, so a filter for ``"fits"`` matches
       ``image.fits``, ``IMG.FITS``, and ``data.Fits``.
   * - ``clear_filters()``
     - Remove all extension filters.  Returns the combobox to just
       "All Files".
   * - ``popup(x=None, y=None)``
     - Show the file browser dialog.  ``x`` and ``y`` are optional
       screen coordinates for the dialog's top-left corner; if
       omitted, the dialog is centered.
   * - ``on(action, callback)``
     - Register a callback for ``action="activated"``.  Fires when
       the user confirms a valid selection.  Callback signature
       depends on mode (see :ref:`fb-modes`).

Icons
~~~~~

The dialog uses SVG icons from ``pgwidgets-js`` for files and folders
by default — they are rendered at a small size in the table column.
A module-level registry maps category names to data: URIs.

.. code-block:: python

   from pgwidgets.extras.file_browser import ICONS, set_icon

   # Override the default file/folder icons
   set_icon("file",   "/path/to/my-file.svg")
   set_icon("folder", "/path/to/my-folder.svg")
   set_icon("parent", "/path/to/up-arrow.svg")

   # Per-extension icons (key is a lowercase extension)
   set_icon("py",  "/path/to/python.svg")
   set_icon("jpg", "/path/to/image.svg")
   set_icon("png", "/path/to/image.svg")

The registered file is read once and embedded as a data: URI, so it
does not need to remain on disk after registration.  PNG, JPEG, GIF,
and SVG are all supported (anything mimetypes recognises as an image
type, plus arbitrary types served as ``application/octet-stream``).

Special category names:

* ``"file"`` — default icon for any file with no extension-specific override.
* ``"folder"`` — icon for directories.
* ``"parent"`` — icon for the ``..`` parent-directory entry.  Defaults
  to the same icon as ``"folder"`` — register a distinct one if you
  want a separate look.

Any other category key is treated as a lowercase file extension and
takes precedence over ``"file"`` when a file with that extension is
listed.  Extension matching is case-insensitive (the registry is
keyed by lowercase extensions, and file names are lowercased before
lookup).

Module API
~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Symbol
     - Description
   * - ``FileBrowser``
     - The dialog class (described above).
   * - ``ICONS``
     - The module-level ``dict`` mapping category name to data: URI.
       Mutate via ``set_icon``; reading is also fine if you want to
       inspect the current registry.
   * - ``set_icon(category, path)``
     - Read an image file and register it under ``category``.
       See :ref:`Icons <fb-modes>` above for category semantics.
