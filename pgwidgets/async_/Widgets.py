"""
Module-level widget classes for the asynchronous API.

All widget classes are built once at import time from the shared
definitions.  They can be imported and subclassed normally::

    from pgwidgets.async_.Widgets import FileDialog, Button

    class MyFileDialog(FileDialog):
        async def pick_file(self):
            await self.open()

Instances are created through the ``get_widgets()`` factory on a
Session, which binds them to a session and handles constructor
argument parsing, state tracking, and callback registration.
"""

from pgwidgets.async_.widget import build_all_widget_classes, Widget

_classes = build_all_widget_classes()
globals().update(_classes)
__all__ = list(_classes.keys()) + ["Widget"]
