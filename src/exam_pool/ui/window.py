from __future__ import annotations

from gi.repository import Adw, Gio, Gtk

from .. import APP_NAME, __version__
from ..data.database import Database
from ..data.packs import PackRepository
from ..domain.models import Pack
from ..settings import Settings
from .home import HomePage
from .preferences import PreferencesDialog
from .stats import StatsView
from .test import TestPage


class MainWindow(Adw.ApplicationWindow):
    def __init__(
        self,
        application: Adw.Application,
        packs: list[Pack],
        db: Database,
        settings: Settings,
        repository: PackRepository,
    ) -> None:
        super().__init__(application=application)
        self._packs = packs
        self._db = db
        self._settings = settings
        self._repository = repository
        self._page_back_state = {"home": False, "test": False, "stats": False}
        width, height = settings.window_size
        self.set_default_size(width, height)
        self.set_title(APP_NAME)

        self._stack = Adw.ViewStack()
        self._stack.set_vexpand(True)
        self._home_page = HomePage(
            packs,
            db,
            settings,
            repository,
            self._on_home_back_state,
        )
        self._test_page = TestPage(
            packs,
            db,
            settings,
            repository,
            self._on_test_back_state,
        )
        self._stats_page = StatsView(
            packs,
            db,
            settings,
            self._open_pool,
        )
        self._stack.add_titled_with_icon(
            self._home_page, "home", "Study", "go-home-symbolic"
        )
        self._stack.add_titled_with_icon(
            self._test_page, "test", "Test", "checkbox-checked-symbolic"
        )
        self._stack.add_titled_with_icon(
            self._stats_page, "stats", "Stats", "utilities-system-monitor-symbolic"
        )

        self._header = Adw.HeaderBar()
        self._switcher = Adw.ViewSwitcher()
        self._switcher.set_stack(self._stack)
        self._header.set_title_widget(self._switcher)

        self._back_button = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self._back_button.set_tooltip_text("Back")
        self._back_button.set_visible(False)
        self._back_button.connect("clicked", self._on_back_clicked)
        self._header.pack_start(self._back_button)

        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_tooltip_text("Main Menu")
        menu = Gio.Menu()
        menu.append("Preferences", "app.preferences")
        menu.append("About Exam Pool", "app.about")
        menu.append("Quit", "app.quit")
        menu_button.set_menu_model(menu)
        self._header.pack_end(menu_button)

        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(self._header)
        toolbar.set_content(self._stack)
        self.set_content(toolbar)

        self._stack.connect("notify::visible-child", self._on_visible_child_changed)
        self.connect("close-request", self._on_close_request)
        self._update_back_button()

    # ------------------------------------------------------------------

    def _on_home_back_state(self, needs_back: bool) -> None:
        self._page_back_state["home"] = needs_back
        self._update_back_button()

    def _on_test_back_state(self, needs_back: bool) -> None:
        self._page_back_state["test"] = needs_back
        self._update_back_button()

    def _on_visible_child_changed(self, _stack, _param) -> None:
        name = self._stack.get_visible_child_name()
        if name == "home":
            self._home_page.refresh()
        elif name == "stats":
            self._stats_page.refresh()
        self._update_back_button()

    def _update_back_button(self) -> None:
        name = self._stack.get_visible_child_name() or "home"
        self._back_button.set_visible(self._page_back_state.get(name, False))

    def _on_back_clicked(self, _button: Gtk.Button) -> None:
        name = self._stack.get_visible_child_name()
        if name == "home":
            self._home_page.back()
        elif name == "test":
            self._test_page.request_back()

    def _open_pool(self, pack: Pack) -> None:
        self._stack.set_visible_child_name("home")
        self._home_page.open_pool(pack)

    def show_preferences(self) -> None:
        dialog = PreferencesDialog(self._settings, self, self._reset_all)
        dialog.present(self)

    def _reset_all(self) -> None:
        self._db.reset_progress()
        self._home_page.back()
        self._home_page.refresh()
        self._test_page.show_setup()
        self._stats_page.refresh()

    def show_about(self) -> None:
        dialog = Adw.AboutDialog()
        dialog.set_application_name(APP_NAME)
        dialog.set_version(__version__)
        dialog.set_developer_name("Exam Pool contributors")
        dialog.set_comments(
            "An offline-first study app for US amateur radio question pools."
        )
        dialog.set_license_type(Gtk.License.GPL_3_0)
        dialog.set_copyright("© 2026 Exam Pool contributors")
        dialog.set_website("https://github.com/gavins/exam-pool")
        dialog.set_issue_url("https://github.com/gavins/exam-pool/issues")
        dialog.present(self)

    def _on_close_request(self, _window: Adw.ApplicationWindow) -> bool:
        width, height = self.get_default_size()
        self._settings.set_window_size(width, height)
        self._test_page.shutdown()
        return False
