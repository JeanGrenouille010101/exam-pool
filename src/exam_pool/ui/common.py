from __future__ import annotations

from gi.repository import Adw, Gtk


def reference_text(reference: str | None) -> str | None:
    if not reference:
        return None
    parts = [part.strip() for part in reference.split(",") if part.strip()]
    if not parts:
        return None
    return "47 CFR " + ", ".join(f"§{part}" for part in parts)


def wrap_label(text: str = "", *, selectable: bool = False) -> Gtk.Label:
    label = Gtk.Label(label=text)
    label.set_wrap(True)
    label.set_xalign(0.0)
    label.set_selectable(selectable)
    return label


def clamp_content(child: Gtk.Widget, maximum_size: int = 760) -> Gtk.Widget:
    scrolled = Gtk.ScrolledWindow()
    scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scrolled.set_vexpand(True)
    clamp = Adw.Clamp()
    clamp.set_maximum_size(maximum_size)
    clamp.set_tightening_threshold(420)
    clamp.set_child(child)
    scrolled.set_child(clamp)
    return scrolled
