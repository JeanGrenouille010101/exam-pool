from __future__ import annotations

from gi.repository import Adw, Gio, Gtk

from .. import APP_NAME, __version__
from ..data.database import Database
from ..data.packs import PackRepository
from ..domain.models import Pack, PackSummary
from ..settings import Settings
from .home import HomePage
from .preferences import PreferencesDialog

_PAGE_TITLES = {"home": "Study", "test": "Test", "stats": "Stats"}


class MainWindow(Adw.ApplicationWindow):
    def __init__(
        self,
        application: Adw.Application,
        packs: list[PackSummary],
        db: Database,
        settings: Settings,
        repository: PackRepository,
    ) -> None:
        super().__init__(application=application)
        self._summaries = packs
        self._db = db
        self._settings = settings
        self._repository = repository
        self._page_back_state = {"home": False, "test": False, "stats": False}
        width, height = settings.window_size
        self.set_default_size(width, height)
        self.set_title(APP_NAME)

        self._stack = Adw.ViewStack()
        self._stack.set_vexpand(True)
        self._test_page = None
        self._stats_page = None
        self._placeholders: dict[str, Gtk.Widget] = {}
        self._home_page = HomePage(
            packs,
            db,
            settings,
            repository,
            self._on_home_back_state,
        )
        self._stack.add_titled_with_icon(
            self._home_page, "home", "Study", "go-home-symbolic"
        )
        for name, title, icon in (
            ("test", "Test", "checkbox-checked-symbolic"),
            ("stats", "Stats", "x-office-spreadsheet-symbolic"),
        ):
            placeholder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            placeholder.set_hexpand(True)
            placeholder.set_vexpand(True)
            self._stack.add_titled_with_icon(placeholder, name, title, icon)
            self._placeholders[name] = placeholder

        self._banner = Adw.Banner()
        self._banner.set_revealed(False)
        self._banner.connect("button-clicked", self._on_banner_button)
        self._banner_action = None

        self._header = Adw.HeaderBar()
        self._switcher = Adw.ViewSwitcher()
        self._switcher.set_stack(self._stack)
        self._window_title = Adw.WindowTitle()
        self._window_title.set_title(_PAGE_TITLES["home"])
        self._window_title.set_visible(False)
        title_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        title_box.set_halign(Gtk.Align.CENTER)
        title_box.append(self._switcher)
        title_box.append(self._window_title)
        self._header.set_title_widget(title_box)
        self._bottom_switcher = Adw.ViewSwitcherBar()
        self._bottom_switcher.set_stack(self._stack)
        self._bottom_switcher.set_reveal(False)
        self._ensure_test_page(show=False)
        breakpoint = Adw.Breakpoint(
            condition=Adw.BreakpointCondition.parse("max-width: 700sp")
        )
        breakpoint.add_setter(self._switcher, "visible", False)
        breakpoint.add_setter(self._window_title, "visible", True)
        breakpoint.add_setter(self._bottom_switcher, "reveal", True)
        for row in self._home_page._home.grid.rows:
            breakpoint.add_setter(row, "orientation", Gtk.Orientation.VERTICAL)
        breakpoint.add_setter(self._home_page._home.note, "visible", False)
        for row in self._test_page._setup.grid.rows:
            breakpoint.add_setter(row, "orientation", Gtk.Orientation.VERTICAL)
        self.add_breakpoint(breakpoint)

        self._back_button = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self._back_button.set_tooltip_text("Back")
        self._back_button.set_visible(False)
        self._back_button.connect("clicked", self._on_back_clicked)
        self._header.pack_start(self._back_button)

        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu_button.set_tooltip_text("Main Menu")
        menu = Gio.Menu()
        menu.append("Check for Question Pool Updates", "app.check-updates")
        menu.append("Preferences", "app.preferences")
        menu.append("About Ohmwork", "app.about")
        menu.append("Quit", "app.quit")
        menu_button.set_menu_model(menu)
        self._header.pack_end(menu_button)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(self._banner)
        content.append(self._stack)
        toolbar = Adw.ToolbarView()
        toolbar.add_top_bar(self._header)
        toolbar.add_bottom_bar(self._bottom_switcher)
        toolbar.set_content(content)
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
        name = self._stack.get_visible_child_name() or "home"
        self._window_title.set_title(_PAGE_TITLES.get(name, APP_NAME))
        if name == "test" and self._test_page is None:
            self._ensure_test_page()
            return
        if name == "stats" and self._stats_page is None:
            self._ensure_stats_page()
            return
        if name == "home":
            self._home_page.refresh()
        elif name == "test" and self._test_page is not None:
            self._test_page.refresh()
        elif name == "stats" and self._stats_page is not None:
            self._stats_page.refresh()
        self._update_back_button()

    def _replace_placeholder(
        self, name: str, page: Gtk.Widget, *, show: bool = True
    ) -> None:
        container = self._placeholders.get(name)
        if container is None:
            return
        page.set_hexpand(True)
        page.set_vexpand(True)
        container.append(page)
        if show:
            self._stack.set_visible_child_name(name)

    def _ensure_test_page(self, *, show: bool = True) -> None:
        from .test import TestPage

        self._test_page = TestPage(
            self._summaries,
            self._db,
            self._settings,
            self._repository,
            self._on_test_back_state,
        )
        self._replace_placeholder("test", self._test_page, show=show)

    def _ensure_stats_page(self) -> None:
        from .stats import StatsView

        self._stats_page = StatsView(
            self._summaries,
            self._db,
            self._settings,
            self._repository,
            self._open_pool,
        )
        self._replace_placeholder("stats", self._stats_page)

    def _update_back_button(self) -> None:
        name = self._stack.get_visible_child_name() or "home"
        self._back_button.set_visible(self._page_back_state.get(name, False))

    def _on_back_clicked(self, _button: Gtk.Button) -> None:
        name = self._stack.get_visible_child_name()
        if name == "home":
            self._home_page.back()
        elif name == "test" and self._test_page is not None:
            self._test_page.request_back()

    def _open_pool(self, pack: Pack) -> None:
        self._stack.set_visible_child_name("home")
        self._home_page.open_pool(pack)

    def show_update_banner(
        self,
        title: str,
        *,
        button_label: str = "Update",
        action=None,
    ) -> None:
        self._banner_action = action
        self._banner.set_title(title)
        self._banner.set_button_label(button_label)
        self._banner.set_revealed(True)

    def hide_update_banner(self) -> None:
        self._banner_action = None
        self._banner.set_revealed(False)

    def _on_banner_button(self, _banner: Adw.Banner) -> None:
        action = self._banner_action
        self._banner_action = None
        if action is not None:
            action()

    def show_preferences(self) -> None:
        dialog = PreferencesDialog(self._settings, self, self._reset_all)
        dialog.present(self)

    def _reset_all(self) -> None:
        self._db.reset_progress()
        self._home_page.discard()
        if self._test_page is not None:
            self._test_page.show_setup()
        if self._stats_page is not None:
            self._stats_page.refresh()

    def show_about(self) -> None:
        dialog = Adw.AboutDialog()
        dialog.set_application_name(APP_NAME)
        dialog.set_version(__version__)
        dialog.set_developer_name("Ohmwork contributors")
        dialog.set_comments(
            "An offline-first amateur radio exam trainer."
        )
        dialog.set_license_type(Gtk.License.GPL_3_0)
        dialog.set_copyright("© 2026 Ohmwork contributors")
        dialog.set_website("https://github.com/JeanGrenouille010101/exam-pool")
        dialog.set_issue_url("https://github.com/JeanGrenouille010101/exam-pool/issues")
        dialog.present(self)

    def _on_close_request(self, _window: Adw.ApplicationWindow) -> bool:
        width, height = self.get_default_size()
        self._settings.set_window_size(width, height)
        self._home_page.pause()
        if self._test_page is not None:
            self._test_page.shutdown()
        return False
