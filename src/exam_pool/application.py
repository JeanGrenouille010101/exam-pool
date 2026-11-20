from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

import os
import threading
from importlib.resources import files

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from . import APP_ID, APP_NAME
from .data.database import Database
from .data.packs import PackRepository
from .data.updates import ContentUpdater, UpdateError
from .paths import content_dir, database_path
from .settings import Settings
from .ui.window import MainWindow


class ExamPoolApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID)
        GLib.set_application_name(APP_NAME)
        self._settings = Settings()
        self._content_dir = content_dir()
        self._repository = PackRepository(
            user_pack_dir=self._content_dir / "packs",
            user_figure_dir=self._content_dir / "figures",
        )
        self._updater = ContentUpdater(
            self._content_dir,
            bundled_figure_dir=self._repository.figure_dir,
        )
        self._summaries = []
        self._db: Database | None = None
        self._window: MainWindow | None = None
        self._update_thread: threading.Thread | None = None
        self._manual_update_check = False
        self._pending_update = None
        self._install_actions()

    def _install_actions(self) -> None:
        for name, callback in (
            ("preferences", self._show_preferences),
            ("about", self._show_about),
            ("check-updates", self._check_updates),
            ("quit", self._quit),
        ):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", callback)
            self.add_action(action)

    def do_startup(self) -> None:
        Adw.Application.do_startup(self)
        self._load_css()
        self._summaries = self._repository.load_summaries()
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
                self._summaries,
                self._db,
                self._settings,
                self._repository,
            )
        self._window.present()
        if os.environ.get("EXAM_POOL_NO_UPDATE_CHECK") != "1":
            self._start_update_check(manual=False)

    # ------------------------------------------------------------------
    # Updates

    def _check_updates(self, _action, _param) -> None:
        self._start_update_check(manual=True)

    def _start_update_check(self, *, manual: bool) -> None:
        if self._update_thread is not None and self._update_thread.is_alive():
            return
        self._manual_update_check = manual
        self._update_thread = threading.Thread(
            target=self._update_check_worker,
            name="exam-pool-update-check",
            daemon=True,
        )
        self._update_thread.start()

    def _update_check_worker(self) -> None:
        try:
            local_paths = {
                pack.id: path
                for pack in self._summaries
                if (path := self._repository.pack_file(pack)) is not None
            }
            update = self._updater.check(
                self._summaries,
                local_pack_paths=local_paths,
            )
        except UpdateError as exc:
            if self._manual_update_check:
                GLib.idle_add(self._show_update_error, str(exc))
            return
        except Exception:  # noqa: BLE001 - background update failures are non-fatal
            if self._manual_update_check:
                GLib.idle_add(self._show_update_error, "Could not check for updates.")
            return
        if update is None:
            if self._manual_update_check:
                GLib.idle_add(self._show_no_update)
            return
        GLib.idle_add(self._show_update_available, update)

    def _show_update_available(self, update) -> bool:
        if self._window is None:
            return GLib.SOURCE_REMOVE
        self._pending_update = update
        self._window.show_update_banner(
            "Question pool update available",
            button_label="Update",
            action=self._download_update,
        )
        return GLib.SOURCE_REMOVE

    def _show_no_update(self) -> bool:
        if self._window is not None:
            self._window.show_update_banner(
                "Question pools are up to date",
                button_label="Dismiss",
                action=self._window.hide_update_banner,
            )
        return GLib.SOURCE_REMOVE

    def _show_update_error(self, message: str) -> bool:
        if self._window is not None:
            self._window.show_update_banner(
                message,
                button_label="Dismiss",
                action=self._window.hide_update_banner,
            )
        return GLib.SOURCE_REMOVE

    def _download_update(self) -> None:
        update = getattr(self, "_pending_update", None)
        if update is None or self._window is None:
            return
        self._window.show_update_banner(
            "Downloading question pool update…",
            button_label="Please wait",
            action=None,
        )
        thread = threading.Thread(
            target=self._download_worker,
            args=(update,),
            name="exam-pool-update-download",
            daemon=True,
        )
        thread.start()

    def _download_worker(self, update) -> None:
        try:
            self._updater.download(update)
        except UpdateError as exc:
            GLib.idle_add(self._show_update_error, str(exc))
            return
        except Exception:  # noqa: BLE001 - background update failures are non-fatal
            GLib.idle_add(self._show_update_error, "Could not install the update.")
            return
        GLib.idle_add(self._show_update_installed)

    def _show_update_installed(self) -> bool:
        if self._window is not None:
            self._window.show_update_banner(
                "Update installed. Restart Exam Pool to use the new question pools.",
                button_label="Quit",
                action=self.quit,
            )
        return GLib.SOURCE_REMOVE

    # ------------------------------------------------------------------

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
