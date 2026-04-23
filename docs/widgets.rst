Widget Reference
================

All widgets are created through the factory namespace returned by
``session.get_widgets()``:

.. code-block:: python

   W = session.get_widgets()
   btn = W.Button("Click me")           # sync
   btn = await W.Button("Click me")     # async

Widget classes can also be imported directly for subclassing — see
:doc:`subclassing` for details.

Every widget inherits common base methods (see `Base Methods`_ below), plus
its own methods listed in each section.

Base Methods
------------

All widgets (except Timer and FileDialog) have these methods:

.. list-table::
   :widths: 40 60
   :header-rows: 1

   * - Method
     - Description
   * - ``resize(width, height)``
     - Set widget size in pixels.
   * - ``get_size()``
     - Return ``[width, height]``.
   * - ``show()``
     - Make the widget visible.
   * - ``hide()``
     - Hide the widget.
   * - ``is_visible()``
     - Return visibility state.
   * - ``set_enabled(tf)``
     - Enable or disable the widget.
   * - ``get_enabled()``
     - Return enabled state.
   * - ``set_tooltip(msg)``
     - Set tooltip text.
   * - ``set_padding(padding)``
     - Set padding in pixels.
   * - ``set_border_width(width)``
     - Set border width.
   * - ``set_border_color(color)``
     - Set border color.
   * - ``set_font(font, size, weight, style)``
     - Set font properties. Pass ``None`` to keep defaults.
   * - ``set_focus()``
     - Give focus to this widget.
   * - ``set_cursor(name)``
     - Set the mouse cursor.
   * - ``add_cursor(name, url, hotspot_x, hotspot_y, size)``
     - Register a custom cursor from an image URL or file path.
   * - ``has_callback(action)``
     - Return True if this widget supports the given callback action.
   * - ``destroy()``
     - Remove the widget from the browser and Python registry.

Container widgets also have ``get_children()``, ``has_callback(action)``, and fire ``child-added`` / ``child-removed`` callbacks.

Callback Registration
~~~~~~~~~~~~~~~~~~~~~

All widgets support two callback registration methods:

.. code-block:: python

   # on() -- handler receives callback args only
   btn.on("activated", lambda: print("clicked"))

   # add_callback() -- handler receives (widget, *callback_args)
   btn.add_callback("activated", lambda w: print(f"{w} clicked"))

See :doc:`callbacks` for details.

.. _layout-containers:

Layout Containers
-----------------

VBox
~~~~

Vertical box layout.

- **Options:** (none)
- **Methods:** ``add_widget(child, stretch)``, ``set_spacing(gap)``
- **Callbacks:** ``child-added``, ``child-removed``

.. code-block:: python

   vbox = Widgets.VBox(spacing=8, padding=10)
   vbox.add_widget(btn, 0)     # stretch=0 means natural size
   vbox.add_widget(label, 1)   # stretch=1 means expand to fill

HBox
~~~~

Horizontal box layout. Same interface as VBox.

- **Methods:** ``add_widget(child, stretch)``, ``set_spacing(gap)``
- **Callbacks:** ``child-added``, ``child-removed``

ButtonBox
~~~~~~~~~

Box layout for buttons. All buttons are sized to match the widest button,
with labels centered.

- **Options:** ``orientation``, ``halign``
- **Methods:** ``add_widget(child, stretch)``, ``insert_widget(index, child, stretch)``,
  ``set_spacing(gap)``, ``set_halign(halign)``
- **Callbacks:** ``child-added``, ``child-removed``

The ``halign`` option controls horizontal alignment of the buttons within
the box: ``'left'``, ``'center'`` (default), or ``'right'``.

GridBox
~~~~~~~

Grid layout.

- **Options:** ``rows``, ``columns``
- **Methods:** ``add_widget(child, row, col)``, ``set_spacing(px)``,
  ``set_row_spacing(px)``, ``set_column_spacing(px)``,
  ``get_row_column_count()``, ``get_widget_at_cell(row, col)``,
  ``insert_row(index, widgets)``, ``append_row(widgets)``,
  ``delete_row(index)``, ``insert_column(index, widgets)``,
  ``append_column(widgets)``, ``delete_column(index)``
- **Callbacks:** ``child-added``, ``child-removed``

Splitter
~~~~~~~~

Resizable split pane.

- **Options:** ``orientation``
- **Methods:** ``add_widget(child)``, ``set_sizes(sizes)``, ``get_sizes()``,
  ``set_minimum_size(child, min_px)``
- **Callbacks:** ``child-added``, ``child-removed``, ``sizing``

Frame
~~~~~

Titled frame (group box).

- **Options:** ``title``
- **Methods:** ``set_widget(child)``, ``set_title(text)``

Expander
~~~~~~~~

Collapsible section.

- **Options:** ``title``, ``collapsible``, ``shadow``
- **Methods:** ``set_widget(child)``, ``toggleContent()``

ScrollArea
~~~~~~~~~~

Scrollable container.

- **Options:** ``hscrollbar``, ``vscrollbar``
- **Methods:** ``set_widget(child)``

TabWidget
~~~~~~~~~

Tabbed container.

- **Options:** ``closable``, ``reorderable``, ``tab_position``
- **Methods:** ``add_widget(child, options)``, ``show_widget(child)``,
  ``close_widget(child)``, ``set_index(index)``, ``get_index()``,
  ``get_tab_id(child)``, ``get_child(tab_id)``, ``index_of(child)``,
  ``highlight_tab(child, bgcolor)``, ``set_tab_position(tabpos)``
- **Callbacks:** ``child-added``, ``child-removed``, ``page-switch``, ``page-close``

.. code-block:: python

   tabs = Widgets.TabWidget(closable=True, tab_position="top")
   tabs.add_widget(panel1, {"title": "Tab 1"})
   tabs.add_widget(panel2, {"title": "Tab 2"})

StackWidget
~~~~~~~~~~~

Stacked pages (like tabs without the tab bar).

- **Methods:** ``add_widget(child, options)``, ``show_widget(child)``,
  ``set_index(index)``, ``get_index()``, ``index_of(child)``,
  ``index_to_widget(index)``
- **Callbacks:** ``child-added``, ``child-removed``, ``page-switch``, ``page-close``

MDIWidget
~~~~~~~~~

Multiple-document interface container.

- **Methods:** ``add_widget(child, options)``, ``cascade_windows()``,
  ``tile_windows()``, ``get_subwin(child)``, ``close_child(child)``,
  ``set_resistance(value)``, ``get_subwindows()``,
  ``move_child(child, x, y)``, ``resize_child(child, width, height)``,
  ``get_child_size(child)``, ``get_child_position(child)``,
  ``index_of(child)``, ``index_to_widget(index)``
- **Callbacks:** ``child-added``, ``child-removed``, ``page-switch``, ``page-close``, ``scrolled``

Windows
-------

TopLevel
~~~~~~~~

A floating window (the primary container for an application).

- **Options:** ``resizable``, ``title``, ``moveable``, ``closeable``
- **Methods:** ``set_widget(child)``, ``set_title(title)``,
  ``set_position(x, y)``, ``set_moveable(tf)``
- **Callbacks:** ``move``, ``close``

.. code-block:: python

   top = Widgets.TopLevel(title="My App", resizable=True)
   top.resize(800, 600)
   top.set_widget(vbox)
   top.show()

Page
~~~~

A page-level container (fills the browser viewport).

- **Methods:** ``set_widget(child)``

Dialog
~~~~~~

Modal or non-modal dialog with buttons. The dialog contains an internal
content area (vertical box layout) where you add your widgets, and an
optional row of buttons at the bottom.

- **Args:** ``title``, ``buttons``
- **Options:** ``autoclose``, ``resizable``, ``moveable``, ``modal``
- **Methods:** ``add_widget(child, stretch)``, ``insert_widget(index, child, stretch)``,
  ``set_spacing(gap)``, ``popup(x, y)``, ``set_modal(tf)``
- **Callbacks:** ``child-added``, ``child-removed``, ``activated`` -- fires with the button value when clicked.

Add content directly to the dialog using ``add_widget()``. The content area
is a vertical box layout, so children stack top-to-bottom with optional
stretch factors, just like ``VBox``.

.. code-block:: python

   dlg = W.Dialog("Confirm", [("OK", True), ("Cancel", False)],
                  modal=True, autoclose=True)
   dlg.set_spacing(8)
   dlg.add_widget(W.Label("Are you sure?"), 0)
   dlg.add_widget(W.TextEntry(text="Reason"), 0)
   dlg.on("activated", lambda val: print(f"Result: {val}"))
   dlg.popup()

.. note::

   ``get_content_area()`` is only available on the JavaScript side.
   On the Python side, use ``add_widget()``, ``insert_widget()``, and
   ``set_spacing()`` directly on the Dialog. This ensures that child
   widgets are properly tracked for browser reconnection.

ColorDialog
~~~~~~~~~~~

Color picker dialog.

- **Options:** ``color``, ``title``, ``modal``, ``moveable``
- **Methods:** ``get_color()``, ``set_color(hex_string)``
- **Callbacks:** ``activated``, ``pick``

Buttons and Controls
--------------------

Button
~~~~~~

- **Args:** ``text``
- **Methods:** ``set_text(text)``, ``set_icon(url, size)``,
  ``set_color(bg, fg)``
- **Callbacks:** ``activated``

.. code-block:: python

   btn = Widgets.Button("Click me")
   btn.on("activated", lambda: print("clicked"))

CheckBox
~~~~~~~~

- **Args:** ``text``
- **Methods:** ``set_state(tf)``, ``get_state()``
- **Callbacks:** ``activated`` -- fires with the new boolean state.

RadioButton
~~~~~~~~~~~

- **Args:** ``text``
- **Options:** ``group``
- **Methods:** ``set_text(text)``, ``set_state(value)``, ``get_state()``
- **Callbacks:** ``activated``

ToggleButton
~~~~~~~~~~~~

- **Args:** ``text``
- **Options:** ``group``
- **Methods:** ``set_text(text)``, ``set_state(value)``, ``get_state()``
- **Callbacks:** ``activated``

Text
----

Label
~~~~~

- **Args:** ``text``
- **Options:** ``halign``
- **Methods:** ``set_text(text)``, ``get_text()``, ``set_color(bg, fg)``,
  ``set_halign(align)``

TextEntry
~~~~~~~~~

Single-line text input.

- **Options:** ``text``, ``editable``, ``linehistory``, ``password``
- **Methods:** ``set_text(text)``, ``get_text()``, ``clear()``,
  ``set_length(numchars)``
- **Callbacks:** ``activated`` -- fires with the entered text.

.. code-block:: python

   entry = Widgets.TextEntry(text="Type here", linehistory=5)
   entry.on("activated", lambda text: print(f"Entered: {text}"))

TextEntrySet
~~~~~~~~~~~~

Text entry with a button.

- **Options:** ``text``, ``value``, ``editable``, ``linehistory``
- **Methods:** ``set_button_text(text)``, ``set_text(text)``, ``get_text()``,
  ``clear()``, ``set_length(numchars)``
- **Callbacks:** ``activated``

TextArea
~~~~~~~~

Multi-line text.

- **Args:** ``text``
- **Options:** ``wrap``, ``editable``
- **Methods:** ``set_text(text)``, ``get_text()``, ``append_text(text)``,
  ``clear()``, ``set_editable(tf)``, ``set_wrap(tf)``,
  ``set_limit(numlines)``

TextSource
~~~~~~~~~~

Source code editor with line numbers, syntax tags, and gutter icons.

- **Args:** ``text``
- **Options:** ``wrap``, ``line_numbers``, ``icon_gutter``, ``editable``,
  ``font_family``, ``font_size``
- **Methods:** ``set_text(text)``, ``get_text()``, ``get_length()``,
  ``insert_text(offset, text, tags)``, ``delete_range(start, end)``,
  ``clear()``, ``set_editable(tf)``, ``set_wrap(mode)``,
  ``set_line_numbers(tf)``, ``set_icon_gutter(tf)``,
  ``set_icon(line, icon_url)``, ``get_cursor()``, ``set_cursor(offset)``,
  ``get_selection()``, ``set_selection(start, end)``,
  ``create_tag(name, attrs)``, ``remove_tag_def(name)``,
  ``apply_tag(name, start, end)``, ``remove_tag(name, start, end)``,
  ``get_tags_at(offset)``, ``create_ref(offset, gravity)``,
  ``remove_ref(ref)``, ``undo()``, ``redo()``, ``can_undo()``,
  ``can_redo()``, ``find(query, opts)``, ``find_all(query, opts)``,
  ``replace(query, replacement, opts)``, ``scroll_to(ref_or_offset)``,
  ``scroll_to_cursor()``
- **Callbacks:** ``changed``, ``cursor_moved``, ``line_clicked``,
  ``icon_clicked``

Selectors
---------

ComboBox
~~~~~~~~

Drop-down selector.

- **Options:** ``editable``, ``dropdown_limit``
- **Methods:** ``append_text(text)``, ``insert_alpha(text)``,
  ``delete_alpha(text)``, ``set_text(text)``, ``get_text()``,
  ``set_index(idx)``, ``get_index()``, ``get_alpha(idx)``, ``clear()``,
  ``set_length(numchars)``
- **Callbacks:** ``activated``

SpinBox
~~~~~~~

Numeric spinner.

- **Options:** ``dtype``, ``min``, ``max``, ``step``, ``value``, ``decimals``
- **Methods:** ``set_value(val)``, ``get_value()``,
  ``set_limits(minval, maxval, incrval)``, ``set_decimals(num)``
- **Callbacks:** ``activated``

Slider
~~~~~~

- **Options:** ``orientation``, ``track``, ``dtype``, ``min``, ``max``,
  ``step``, ``value``, ``show_value``, ``show_value_position``, ``decimals``
- **Methods:** ``set_value(num)``, ``get_value()``,
  ``set_limits(minval, maxval, incrval)``, ``set_tracking(track)``,
  ``set_decimals(num)``
- **Callbacks:** ``activated``

The ``show_value`` option (default ``False``) displays the current value.
``show_value_position`` controls placement: ``'r'`` (right, default),
``'l'`` (left), ``'t'`` (top), ``'b'`` (bottom).
``decimals`` sets fixed decimal places for the display (default: auto from step).

.. code-block:: python

   slider = Widgets.Slider(min=0, max=100, value=50, track=True)
   slider.on("activated", lambda val: print(f"Value: {val}"))

Dial
~~~~

Rotary dial control.

- **Options:** ``track``, ``dtype``, ``min``, ``max``, ``step``, ``value``,
  ``show_value``, ``show_value_position``, ``decimals``
- **Methods:** ``set_value(num)``, ``get_value()``,
  ``set_limits(minval, maxval, incrval)``, ``set_tracking(track)``,
  ``set_decimals(num)``, ``set_knob_diameter(len_px)``, ``set_icon(url, size)``
- **Callbacks:** ``activated``

The ``show_value`` option (default ``False``) displays the current value.
``show_value_position`` controls placement: ``'b'`` (bottom, default),
``'ur'`` (upper right), ``'ul'`` (upper left), ``'lr'`` (lower right),
``'ll'`` (lower left).
``decimals`` sets fixed decimal places for the display (default: auto from step).

ScrollBar
~~~~~~~~~

- **Options:** ``orientation``, ``thickness``
- **Methods:** ``set_scroll_percent(pct)``, ``get_scroll_percent()``,
  ``set_thumb_percent(pct)``
- **Callbacks:** ``activated``

ProgressBar
~~~~~~~~~~~

- **Methods:** ``set_value(value)``, ``get_value()``

Color
-----

ColorWidget
~~~~~~~~~~~

Inline color picker.

- **Options:** ``color``
- **Methods:** ``get_color()``, ``set_color(hex_string)``
- **Callbacks:** ``pick``

Data Display
------------

Image
~~~~~

Displays an image. Can be interactive for drawing and input events.

- **Options:** ``url``, ``interactive``, ``use_animation_frame``
- **Methods:** ``set_image(url)``, ``get_draw_context()``, ``update()``
- **Callbacks:** ``pointer-down``, ``pointer-up``, ``pointer-move``,
  ``enter``, ``leave``, ``click``, ``dblclick``, ``scroll``,
  ``key-down``, ``key-up``, ``key-press``, ``focus-in``, ``focus-out``,
  ``drop-start``, ``drop-end``, ``drag-over``, ``drop-progress``,
  ``contextmenu``

Canvas
~~~~~~

HTML5 canvas for custom drawing.

- **Options:** ``use_animation_frame``, ``interactive``
- **Methods:** ``draw_image(imgInfo)``, ``get_draw_context()``, ``update()``
- **Callbacks:** Same interactive callbacks as Image, plus ``activated``.

TreeView
~~~~~~~~

Hierarchical tree/list display.

- **Options:** ``columns``, ``show_header``, ``selection_mode``,
  ``alternate_row_colors``, ``show_grid``, ``show_row_numbers``
- **Methods:** ``set_columns(columns)``, ``set_tree(data)``,
  ``set_data(data)``, ``add_item(parent, values)``,
  ``remove_item(node)``, ``update_tree(items)``,
  ``remove_items(paths)``, ``clear()``, ``expand_all()``,
  ``collapse_all()``, ``get_expanded()``, ``get_collapsed()``,
  ``expand_item(node)``, ``collapse_item(node)``, ``get_selected()``,
  ``set_selected(items)``, ``select_path(path, state)``,
  ``select_paths(paths, state)``, ``select_all(state)``,
  ``set_column_width(col_index, width)``,
  ``set_optimal_column_widths()``,
  ``sort_by_column(col_index, ascending)``, ``scroll_to_path(path)``,
  ``scroll_to_end()``, ``get_column_count()``, ``get_row_count()``,
  ``set_show_grid(tf)``, ``set_show_row_numbers(tf)``,
  ``set_column_editable(col_index, tf)``,
  ``set_cell(row, col_index, value)``,
  ``insert_column(index, column)``, ``append_column(column)``,
  ``delete_column(index)``, ``insert_row(index, values)``,
  ``append_row(values)``, ``delete_row(index)``
- **Callbacks:** ``activated``, ``selected``, ``expanded``, ``collapsed``,
  ``cell_edited``

TableView
~~~~~~~~~

Flat table display. Same column/selection interface as TreeView but without
tree hierarchy.

- **Options:** ``columns``, ``show_header``, ``selection_mode``,
  ``alternate_row_colors``, ``show_grid``, ``show_row_numbers``
- **Methods:** ``set_columns(columns)``, ``set_rows(rows)``,
  ``set_data(data)``, ``clear()``, ``get_selected()``,
  ``set_selected(items)``, ``select_path(path, state)``,
  ``select_paths(paths, state)``, ``select_all(state)``,
  ``set_column_width(col_index, width)``,
  ``set_optimal_column_widths()``,
  ``sort_by_column(col_index, ascending)``, ``scroll_to_path(path)``,
  ``scroll_to_end()``, ``get_column_count()``, ``get_row_count()``,
  ``set_show_grid(tf)``, ``set_show_row_numbers(tf)``,
  ``set_column_editable(col_index, tf)``,
  ``set_cell(row, col_index, value)``,
  ``insert_column(index, column)``, ``append_column(column)``,
  ``delete_column(index)``, ``insert_row(index, values)``,
  ``append_row(values)``, ``delete_row(index)``
- **Callbacks:** ``activated``, ``selected``, ``cell_edited``

Non-Visual
----------

Timer
~~~~~

Non-visual timer. Created via ``session.make_timer()`` or the widget factory.

- **Options:** ``duration``
- **Methods:** ``start(duration)``, ``stop()``, ``cancel()``, ``is_set()``,
  ``elapsed_time()``, ``time_left()``, ``set_duration(duration)``,
  ``get_duration()``
- **Callbacks:** ``expired``, ``cancelled``

.. code-block:: python

   timer = session.make_timer(duration=5000)  # 5 seconds
   timer.on("expired", lambda: print("Timer fired!"))
   timer.start()

FileDialog
~~~~~~~~~~

Browser file open/save dialog.

- **Options:** ``mode``, ``accept``
- **Methods:** ``open()``, ``save(filename, data, mime_type)``,
  ``set_mode(mode)``, ``get_mode()``, ``set_accept(accept)``,
  ``get_accept()``
- **Callbacks:** ``activated``, ``progress``

Menus and Toolbars
------------------

MenuBar
~~~~~~~

- **Methods:** ``add_menu(menu, name)``, ``add_name(name)``,
  ``get_menu(name)``

Menu
~~~~

- **Methods:** ``add_widget(child)``, ``add_name(name, checkable)``,
  ``add_menu(name, menu)``, ``add_separator()``, ``popup()``

MenuAction
~~~~~~~~~~

- **Options:** ``text``, ``icon_url``, ``iconsize``, ``checkable``, ``name``
- **Methods:** ``set_text(text)``, ``get_text()``, ``set_icon(url, iconsize)``,
  ``set_checked(checked)``, ``get_checked()``
- **Callbacks:** ``activated``

ToolBar
~~~~~~~

- **Options:** ``orientation``
- **Methods:** ``add_widget(child)``, ``add_separator()``, ``add_spacer()``,
  ``add_action(options)``

ToolBarAction
~~~~~~~~~~~~~

- **Options:** ``text``, ``icon_url``, ``iconsize``, ``toggle``, ``group``,
  ``menu``
- **Methods:** ``set_text(text)``, ``get_text()``, ``set_icon(url, iconsize)``,
  ``set_state(value)``, ``get_state()``, ``set_menu(menu)``
- **Callbacks:** ``activated``

The ``menu`` option attaches a ``Menu`` widget that pops up when the action
is clicked. Supports click-and-hold (drag to select) and click-to-toggle
(click to open, click again or select to close) interaction.
