"""
Module-level widget classes for the synchronous API.

All widget classes are built once at import time from the shared
definitions.  They can be imported and subclassed normally::

    from pgwidgets.sync.Widgets import FileDialog, Button

    class MyFileDialog(FileDialog):
        def pick_file(self):
            self.open()

Instances are created through the ``get_widgets()`` factory on a
Session, which binds them to a session and handles constructor
argument parsing, state tracking, and callback registration.
"""

from pgwidgets.sync.widget import build_all_widget_classes, Widget

_classes = build_all_widget_classes()
globals().update(_classes)
__all__ = list(_classes.keys()) + ["Widget"]
