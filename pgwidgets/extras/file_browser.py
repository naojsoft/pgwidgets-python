"""
Local file browser dialog.

A composite widget that lets the user browse the server's filesystem
and select files, folders, or a save location.  Built entirely from
existing pgwidgets widgets (Dialog, TableView, TextEntry, etc.) with
all filesystem I/O happening on the Python side.

Usage (sync API)::

    fd = FileBrowser(session, mode="file", title="Open File")
    fd.add_ext_filter("Images", "png")
    fd.add_ext_filter("Images", "jpg")
    fd.on("activated", lambda path: print(f"Selected: {path}"))
    fd.popup()
"""

import os
import stat
import time

# ── Icon data URIs ──────────────────────────────────────────────
# Simple SVG icons encoded as data URIs.  Kept as module-level
# constants so they are easy to extend for new file types.

_ICON_FOLDER = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E"
    "%3Cpath d='M1 3h5l1.5-1.5H15v11H1z' fill='%23e8a735' "
    "stroke='%23c48820' stroke-width='0.5'/%3E"
    "%3Cpath d='M1 4.5h14v8.5H1z' fill='%23f0c050'/%3E"
    "%3C/svg%3E"
)

_ICON_FILE = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E"
    "%3Cpath d='M3 1h7l3 3v11H3z' fill='%23f0f0f0' "
    "stroke='%23999' stroke-width='0.5'/%3E"
    "%3Cpath d='M10 1v3h3' fill='none' stroke='%23999' "
    "stroke-width='0.5'/%3E"
    "%3C/svg%3E"
)

_ICON_PARENT = (
    "data:image/svg+xml,"
    "%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E"
    "%3Cpath d='M1 3h5l1.5-1.5H15v11H1z' fill='%23c0c0c0' "
    "stroke='%23999' stroke-width='0.5'/%3E"
    "%3Cpath d='M5 8h6M8 5.5v5' stroke='%23666' stroke-width='1.5' "
    "fill='none'/%3E"
    "%3C/svg%3E"
)

# Maps lowercase file extension to icon data URI.
# Extend this dict to add icons for known file types.
ICON_BY_EXT = {
    # Add per-extension overrides here, e.g.:
    # "py": _ICON_PYTHON,
    # "jpg": _ICON_IMAGE,
}

# Default icons by entry type
ICON_FOLDER = _ICON_FOLDER
ICON_FILE = _ICON_FILE
ICON_PARENT = _ICON_PARENT


def _icon_for_name(name, is_dir):
    """Return the icon data URI for a filename."""
    if is_dir:
        return ICON_FOLDER
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    return ICON_BY_EXT.get(ext, ICON_FILE)


def _format_size(size_bytes):
    """Format a byte count as a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


def _format_time(mtime):
    """Format a modification time as a readable date string."""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))


class FileBrowser:
    """A file browser dialog built from pgwidgets widgets.

    Parameters
    ----------
    session : Session
        The pgwidgets session.
    title : str
        Dialog title.
    modal : bool
        Whether the dialog is modal.
    autoclose : bool
        Whether the dialog closes after selection.
    mode : str
        One of ``"file"``, ``"files"``, ``"directory"``, ``"save"``.
    """

    def __init__(self, session, title="Browse", modal=True, autoclose=True,
                 mode="file"):
        W = session.get_widgets()
        self._W = W
        self._mode = mode
        self._autoclose = autoclose
        self._directory = os.getcwd()
        self._directory_set = False
        self._filename = None
        self._show_hidden = False
        self._filters = {}      # category -> [ext, ...]
        self._active_filter = None  # None = all files
        self._callbacks = []
        self._selected_names = []

        # Determine button labels
        if mode == "save":
            ok_label = "Save"
        elif mode == "directory":
            ok_label = "Select"
        else:
            ok_label = "Open"

        # Build the dialog (autoclose=False; we manage closing ourselves)
        self._dialog = W.Dialog(title, [["Cancel", "cancel"],
                                         [ok_label, "ok"]],
                                autoclose=False, modal=modal,
                                moveable=True, resizable=True)
        self._dialog.resize(550, 420)
        self._dialog.set_spacing(6)
        self._dialog.set_padding(4)

        # ── Path bar ──
        path_bar = W.HBox(spacing=4)

        self._btn_up = W.Button("↑")
        self._btn_up.on("activated", self._go_up)
        path_bar.add_widget(self._btn_up, 0)

        self._path_entry = W.TextEntry()
        self._path_entry.on("activated", self._on_path_entered)
        path_bar.add_widget(self._path_entry, 1)

        self._dialog.add_widget(path_bar, 0)

        # ── File table ──
        self._table = W.TableView(
            columns=[
                {"label": "", "type": "icon", "icon_size": 16},
                {"label": "Name", "type": "string"},
                {"label": "Size", "type": "string"},
                {"label": "Modified", "type": "string"},
            ],
            selection_mode="multiple" if mode == "files" else "single",
            alternate_row_colors=True,
            sortable=True,
        )
        self._table.set_column_width(0, 24)
        self._table.on("activated", self._on_row_activated)
        self._table.on("selected", self._on_row_selected)
        self._dialog.add_widget(self._table, 1)

        # ── Bottom bar ──
        bottom = W.VBox(spacing=4)

        # Filename entry (save mode or for showing selection)
        name_row = W.HBox(spacing=4)
        name_row.add_widget(W.Label("Name:"), 0)
        self._name_entry = W.TextEntry()
        self._name_entry.set_length(40)
        name_row.add_widget(self._name_entry, 1)
        bottom.add_widget(name_row, 0)

        # Filter combobox
        filter_row = W.HBox(spacing=4)
        filter_row.add_widget(W.Label("Filter:"), 0)
        self._filter_combo = W.ComboBox()
        self._filter_combo.append_text("All Files")
        self._filter_combo.set_index(0)
        self._filter_combo.on("activated", self._on_filter_changed)
        filter_row.add_widget(self._filter_combo, 1)
        bottom.add_widget(filter_row, 0)

        self._dialog.add_widget(bottom, 0)

        # Dialog button handling
        self._dialog.on("activated", self._on_dialog_button)

    # ── Public API ──────────────────────────────────────────────

    def set_mode(self, mode):
        """Set the selection mode: 'file', 'files', 'directory', 'save'."""
        self._mode = mode

    def set_directory(self, path):
        """Set the directory to browse."""
        self._directory = os.path.abspath(path)
        self._directory_set = True

    def set_filename(self, name):
        """Pre-select a filename or folder name."""
        self._filename = name

    def clear_filters(self):
        """Remove all file extension filters."""
        self._filters.clear()
        self._rebuild_filter_combo()

    def add_ext_filter(self, category, file_ext):
        """Add a file extension filter.

        Parameters
        ----------
        category : str
            Display name (e.g. "Images").
        file_ext : str
            Extension without dot (e.g. "png", "jpg").
        """
        file_ext = file_ext.lstrip(".")
        self._filters.setdefault(category, []).append(file_ext.lower())
        self._rebuild_filter_combo()

    def popup(self, x=None, y=None):
        """Show the file browser dialog."""
        if not self._directory_set:
            # Use cwd only on first open if not explicitly set
            self._directory = os.getcwd()
        self._populate()
        self._dialog.popup(x, y)

    def on(self, action, callback):
        """Register a callback.

        The ``'activated'`` callback is fired with the selected path
        (a string) for single-selection modes, or a list of paths for
        ``mode='files'``.
        """
        if action == "activated":
            self._callbacks.append(callback)

    # ── Internal ────────────────────────────────────────────────

    def _rebuild_filter_combo(self):
        """Rebuild the filter combobox from current filters."""
        self._filter_combo.clear()
        self._filter_combo.append_text("All Files")
        for category, exts in self._filters.items():
            ext_str = ", ".join(f"*.{e}" for e in exts)
            self._filter_combo.append_text(f"{category} ({ext_str})")
        self._filter_combo.set_index(0)
        self._active_filter = None

    def _get_active_extensions(self):
        """Return the set of allowed extensions, or None for all."""
        if self._active_filter is None:
            return None
        return set(self._active_filter)

    def _populate(self):
        """Read the current directory and fill the table."""
        self._path_entry.set_text(self._directory)

        entries = []
        try:
            for name in os.listdir(self._directory):
                if not self._show_hidden and name.startswith("."):
                    continue
                full = os.path.join(self._directory, name)
                try:
                    st = os.stat(full)
                except OSError:
                    continue
                is_dir = stat.S_ISDIR(st.st_mode)
                entries.append((name, is_dir, st.st_size, st.st_mtime))
        except OSError:
            pass

        # Sort: directories first, then alphabetical (case-insensitive)
        entries.sort(key=lambda e: (not e[1], e[0].lower()))

        # Filter files by extension
        allowed = self._get_active_extensions()

        rows = []
        # Parent directory entry
        parent = os.path.dirname(self._directory)
        if parent != self._directory:  # not at root
            rows.append([ICON_PARENT, "..", "", ""])

        for name, is_dir, size, mtime in entries:
            if not is_dir and allowed is not None:
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if ext not in allowed:
                    continue
            icon = _icon_for_name(name, is_dir)
            size_str = "" if is_dir else _format_size(size)
            time_str = _format_time(mtime)
            rows.append([icon, name, size_str, time_str])

        self._table.set_rows(rows)
        self._table.set_column_width(0, 24)

        # Pre-select filename if set
        if self._filename:
            self._name_entry.set_text(self._filename)
            self._filename = None
        else:
            self._name_entry.set_text("")

    def _navigate_to(self, path):
        """Navigate to a directory."""
        path = os.path.abspath(path)
        if os.path.isdir(path):
            self._directory = path
            self._populate()

    def _go_up(self):
        """Navigate to the parent directory."""
        parent = os.path.dirname(self._directory)
        if parent != self._directory:
            self._navigate_to(parent)

    def _on_path_entered(self):
        """User pressed Enter in the path entry."""
        path = self._path_entry.get_text().strip()
        if os.path.isdir(path):
            self._navigate_to(path)
        else:
            # Maybe they typed a file path — navigate to its directory
            d = os.path.dirname(path)
            if os.path.isdir(d):
                self._navigate_to(d)
                self._name_entry.set_text(os.path.basename(path))

    def _on_row_activated(self, values):
        """Double-click on a row."""
        name = values[1]  # column 1 is the name
        if name == "..":
            self._go_up()
            return

        full = os.path.join(self._directory, name)
        if os.path.isdir(full):
            self._navigate_to(full)
        else:
            # Double-click on a file: select it
            self._name_entry.set_text(name)
            if self._mode != "directory":
                self._accept()

    def _on_filter_changed(self, index, text):
        """Filter combobox selection changed."""
        if index <= 0:
            self._active_filter = None
        else:
            # Map combo index back to filter category
            categories = list(self._filters.keys())
            if index - 1 < len(categories):
                self._active_filter = self._filters[categories[index - 1]]
            else:
                self._active_filter = None
        self._populate()

    def _on_dialog_button(self, value):
        """Dialog button pressed."""
        if value == "ok":
            self._accept()
        else:
            # Cancel — just hide, no callback
            self._dialog.hide()

    def _accept(self):
        """Validate selection and fire callback."""
        name = self._name_entry.get_text().strip()

        if self._mode == "files":
            # Gather all selected file paths
            # (we stored full rows, need to resolve paths)
            selected = self._gather_selected_paths()
            if selected:
                self._close_and_fire(selected)
            return

        if not name:
            return

        full = os.path.join(self._directory, name)

        if self._mode == "directory":
            if os.path.isdir(full):
                self._close_and_fire(full)
        elif self._mode == "save":
            if os.path.isdir(full):
                # Navigate into the directory instead
                self._navigate_to(full)
                return
            if os.path.exists(full):
                self._confirm_overwrite(full)
            else:
                self._close_and_fire(full)
        else:  # mode == "file"
            if os.path.isdir(full):
                self._navigate_to(full)
            elif os.path.isfile(full):
                self._close_and_fire(full)

    def _gather_selected_paths(self):
        """Build list of selected file paths (for mode='files')."""
        if self._selected_names:
            return [os.path.join(self._directory, n)
                    for n in self._selected_names
                    if os.path.isfile(os.path.join(self._directory, n))]
        name = self._name_entry.get_text().strip()
        if name and os.path.isfile(os.path.join(self._directory, name)):
            return [os.path.join(self._directory, name)]
        return []

    def _confirm_overwrite(self, path):
        """Show a confirmation dialog for overwriting an existing file."""
        W = self._W
        dlg = W.Dialog("Confirm Overwrite",
                        [["Cancel", "cancel"], ["Overwrite", "ok"]],
                        autoclose=True, modal=True)
        dlg.resize(350, 140)
        dlg.set_spacing(8)
        name = os.path.basename(path)
        dlg.add_widget(
            W.Label(f'"{name}" already exists. Overwrite?'), 1)

        def on_confirm(value):
            if value == "ok":
                self._close_and_fire(path)

        dlg.on("activated", on_confirm)
        dlg.popup()

    def _close_and_fire(self, result):
        """Hide the dialog and fire callbacks."""
        if self._autoclose:
            self._dialog.hide()
        for cb in self._callbacks:
            cb(result)

    def _on_row_selected(self, items):
        """Selection changed in the table."""
        if not items:
            self._selected_names = []
            return
        names = [it["values"][1] for it in items
                 if it["values"][1] != ".."]
        self._selected_names = names

        if self._mode == "files":
            if len(names) == 1:
                self._name_entry.set_text(names[0])
            elif names:
                self._name_entry.set_text(f"{len(names)} items selected")
        else:
            if names:
                self._name_entry.set_text(names[0])
