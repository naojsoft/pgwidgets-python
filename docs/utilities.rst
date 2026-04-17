Utilities
=========

The ``Widget`` base class exposes a few static utility methods that are
useful when working with local files on the server side.

.. code-block:: python

   from pgwidgets.sync.widget import Widget   # or pgwidgets.async_.widget

to_data_uri
------------

.. code-block:: python

   Widget.to_data_uri(path)

Read a local file, base64-encode its contents, and return a
``data:<mime>;base64,…`` string.  The MIME type is guessed from the file
extension (falls back to ``application/octet-stream``).

The returned string can be passed directly to any widget method that
expects a URL, such as ``set_image()``, ``set_icon()``, or
``add_cursor()``.

.. code-block:: python

   # Load a local image into an Image widget
   img.set_image(Widget.to_data_uri("/path/to/photo.png"))

   # Set a button icon from a local file
   btn.set_icon(Widget.to_data_uri("/path/to/icon.svg"))

.. note::

   Methods listed in the ``_FILE_ARG_METHODS`` set (currently
   ``set_icon``, ``set_image``, and ``set_icon_gutter``) already detect
   local file paths and convert them automatically.  Use
   ``to_data_uri()`` explicitly when you need the data URI for other
   purposes or want to cache/reuse it.
