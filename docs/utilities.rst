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


Buffer
------

.. code-block:: python

   from pgwidgets import Buffer

   pixels = numpy_array.tobytes()            # 2048 * 2048 * 4 bytes
   buf = Buffer(pixels,
                shape=(2048, 2048, 4),
                dtype="uint8")
   viewer.load_buffer(buf, [2048, 2048], cache)

A ``Buffer`` wraps raw ``bytes`` with ``shape`` and ``dtype``
metadata, so a method receiving the buffer on the JavaScript side
gets a properly-sized typed array (``Uint8Array``, ``Float32Array``,
…) instead of a raw ``ArrayBuffer``.  Use it for image pixel data,
scientific arrays, vertex buffers — anything where the receiver
needs to know how to interpret the bytes without a hand-rolled
convention per method.

A ``Buffer`` always ships via the chunked binary transport
(``binary-call-chunked`` + ``binary-chunk`` messages), so multi-
megabyte payloads stream in 512 KiB chunks and don't block other
WebSocket traffic.  ``shape`` and ``dtype`` ride on the announce
header — see :doc:`architecture`.

Supported dtypes:

- ``"uint8"`` / ``"uint16"`` / ``"uint32"``
- ``"int8"`` / ``"int16"`` / ``"int32"``
- ``"float32"`` / ``"float64"``

Methods that don't opt into ``Buffer`` keep receiving plain
``bytes`` — :class:`Buffer` is purely additive.  Construction
validates that the byte length equals
``prod(shape) * dtype.itemsize``; pass ``shape=(len(data),)`` and
``dtype="uint8"`` if you just want a flat byte buffer with a
known length.
