from __future__ import annotations

from collections.abc import Callable

from gi.repository import Adw, GLib, Gtk


def confirm(
    parent: Gtk.Widget,
    *,
    heading: str,
    body: str,
    confirm_label: str,
    on_confirm: Callable[[], None],
) -> None:
    dialog = Adw.AlertDialog()
    dialog.set_heading(heading)
    dialog.set_body(body)
    dialog.add_response("cancel", "Cancel")
    dialog.add_response("confirm", confirm_label)
    dialog.set_default_response("confirm")
    dialog.set_close_response("cancel")

    def finished(dialog: Adw.AlertDialog, result) -> None:
        try:
            response = dialog.choose_finish(result)
        except GLib.Error:
            return
        if response == "confirm":
            on_confirm()

    dialog.choose(parent, None, finished)
