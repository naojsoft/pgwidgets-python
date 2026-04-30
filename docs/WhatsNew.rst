What's New
==========

Significant changes since the last tagged release (``v0.1.3``).

Major changes
-------------

TreeView / TableView: dict-tree model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Mirroring the JS-side rewrite, ``TreeView`` and ``TableView`` now
work with hierarchies of dicts keyed by stable string identifiers.
Paths are arrays of those keys and stay valid no matter how the
visible tree is sorted.

.. code-block:: python

   tree = W.TreeView(columns=[
       {"label": "Name", "key": "NAME", "type": "string"},
       {"label": "Type", "key": "TYPE", "type": "string"},
       {"label": "Size", "key": "SIZE", "type": "integer"},
   ], sortable=True)

   tree.set_tree({
       "Documents": {
           "report.pdf": {"TYPE": "PDF",  "SIZE": 2400},
           "notes.txt":  {"TYPE": "Text", "SIZE": 12},
       },
       "Pictures": {
           "photo.jpg": {"TYPE": "JPEG", "SIZE": 3200},
       },
   })

Highlights:

- New column-key-based API: ``set_column_width(col_key)``,
  ``sort_by_column(col_key, ascending)``,
  ``insert_column(column, before=None)``,
  ``delete_column(col_key)``,
  ``set_cell(path, col_key, value)``,
  ``set_column_editable(col_key, tf)``.
- New column types: ``"string"`` / ``"integer"`` / ``"float"`` /
  ``"boolean"`` (renders ✓ when truthy) / ``"icon"``.
  ``halign`` field with sensible per-type defaults.
- New tree methods:

  - ``add_tree(tree, parent=None)`` -- merge a dict-tree under a
    parent path (preserves selection by path).
  - ``update_tree(tree)`` -- replace the tree, preserve selection.
  - ``get_subtree(status='all')`` -- return a connected subset
    (selected / expanded / collapsed nodes plus their descendants
    and ancestors), round-trippable through ``set_tree``.
  - ``clear_selection()`` -- explicit no-arg reset.

- Auto-spanning: a row whose value for a column is missing causes
  the previous present cell to extend across it.  Lets parent rows
  be terse: ``{"NAME": "Documents"}`` (with the rest of the columns
  omitted) renders as a single cell across the row.
- ``TableView.set_data`` accepts a list of dicts (preferred) or a
  list of arrays.

See :doc:`widgets` for the full reference.

Window controls (TopLevel) and shade (MDISubWindow)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``TopLevel`` gains the same window controls that ``MDISubWindow``
has, plus a "shade" (roll up to title bar) state on both.

New ``TopLevel`` options (default ``False`` except ``shadeable``
which defaults ``True``):

- ``minimizable`` -- show minimize button.  Minimized windows
  auto-stack along the bottom of the viewport.
- ``maximizable`` -- show maximize button.  Fills the browser
  viewport (snapshot at click time).
- ``lowerable`` -- show send-to-back button.
- ``shadeable`` -- collapse to title bar in place.  Available from
  the right-click context menu and via double-click on the title
  bar.
- ``icon`` -- title-bar icon (URL or ``data:`` URI).

New methods: ``set_icon(url)``, ``toggle_minimize()``,
``toggle_maximize()``, ``toggle_shade()``,
``set_window_state(state)``, ``get_window_state()``.

New callback ``window-state`` is auto-tracked, so the
minimize/maximize/shade state survives a browser reconnect.

``MDIWidget.add_widget`` accepts ``shadeable`` (default ``True``).

Right-click on the title bar of either widget opens a context menu
with the applicable actions (Raise, Lower, Shade, Minimize,
Maximize, Close).  The menu supports both click-release and
press-drag-release, like a menubar.

Image: binary-frame protocol
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

New method ``Image.set_binary_image(data, format='jpeg')`` sends raw
bytes (``bytes`` / ``bytearray`` / ``memoryview``) via a WebSocket
binary frame, avoiding the ~33% base64 overhead of ``set_image``.
Useful for animation/streaming.  ``format`` is one of ``"jpeg"``,
``"png"``, ``"webp"``, ``"gif"``.  The latest frame is stored in
widget state and replayed on reconnect.

Callbacks base class
~~~~~~~~~~~~~~~~~~~~

New module ``pgwidgets.callbacks`` exposes ``Callbacks``, a small
base class that provides the same callback API (``add_callback``,
``on``, ``make_callback``, ``enable_callback``, ...) as a real
``Widget`` without the widget machinery.  Use it for Python-side
composite/utility classes that need to expose handler registration.

``FileBrowser`` (in ``pgwidgets.extras``) is now a subclass and so
supports both ``add_callback("activated", ...)`` and
``on("activated", ...)`` directly.

See :ref:`callbacks-base`.

Robustness improvements
-----------------------

- ``Session._send`` and ``_send_binary`` no longer hang when the
  asyncio loop refuses a coroutine (loop closed mid-call,
  ``RecursionError`` from a deep callback chain, etc.).  The
  schedule failure is logged, the orphan coroutine is closed, and
  ``_send`` returns ``None`` so the caller continues.
- ``json.dumps`` errors in ``_send`` / ``_push`` are caught and
  logged instead of crashing reconstruction with a non-JSON-
  serialisable widget state.
- After every ``create``, ``Session._next_wid`` is advanced past
  the JS-side ``next_wid`` so subsequent Python allocations skip
  any auto-allocated sub-widget IDs (matching the JS-side
  collision rescue).  This fixes "callback fires on the wrong
  widget" cases where a widget like ``TreeView`` allocates
  internal ``ScrollBar`` widgets in its constructor.

Other notable changes
---------------------

- ``ColorDialog`` now exposes ``popup``, ``set_position``,
  ``set_modal``, and the ``move`` / ``close`` callbacks (inherited
  from ``Dialog`` on the JS side).  Its ``popup`` is wired through
  the ``_dialog_popup`` custom method so visibility/position state
  is tracked for reconstruction.
- ``MenuAction`` ``activated`` callback signature simplified.  Old:
  ``handler(widget, text, checked)``.  New: ``handler(widget)`` for
  non-checkable actions; ``handler(widget, checked)`` for checkable
  ones.  *This is a breaking change for any handler that took the
  text arg.*
- ``Widget`` base class now exposes
  ``set_allow_text_selection(tf)``; browser text selection is off
  by default for most widgets (form controls and the cell editor
  in ``TreeView`` always allow selection).
- ``clear()`` on ``TreeView`` / ``TableView`` no longer resets the
  ``columns`` state (it was popping ``_state["columns"]`` even
  though the JS side preserves columns on clear).
- ``FileBrowser`` migrated to the new dict-tree ``TableView`` API
  internally and now subclasses ``Callbacks``.
