from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from importlib.resources import files

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import APP_ID, APP_NAME
from .data.database import Database
from .data.packs import PackRepository
from .paths import database_path
from .settings import Settings
from .ui.window import MainWindow


class ExamPoolApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID)
        GLib.set_application_name(APP_NAME)
        self._settings = Settings()
        self._repository = PackRepository()
        self._packs = []
        self._db: Database | None = None
        self._window: MainWindow | None = None
        self._install_actions()

    def _install_actions(self) -> None:
        for name, callback in (
            ("preferences", self._show_preferences),
            ("about", self._show_about),
            ("quit", self._quit),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._load_css()
        self._packs = self._repository.load_all()
        self._db = Database(database_path())

    def _load_css(self) -> None:
        css_path = files("exam_pool").joinpath("resources/style.css")
        provider = Gtk.CssProvider()
        provider.load_from_data(css_path.read_bytes())
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display,
                provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

    def do_activate(self) -> None:
        if self._window is None:
            assert self._db is not None
            self._window = MainWindow(
                self,
                self._packs,
                self._db,
                self._settings,
                self._repository,
            )
        self._window.present()

    def _show_preferences(self, _action, _param) -> None:
        if self._window is not None:
            self._window.show_preferences()

    def _show_about(self, _action, _param) -> None:
        if self._window is not None:
            self._window.show_about()

    def _quit(self, _action, _param) -> None:
        self.quit()

    def do_shutdown(self) -> None:
        if self._db is not None:
            self._db.close()
        Adw.Application.do_shutdown(self)
