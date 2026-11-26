from __future__ import annotations

from collections.abc import Callable

from gi.repository import Adw, Gtk

from ..data.database import Database
from ..data.packs import PackRepository
from ..domain.models import Pack, PackSummary
from ..settings import Settings
from .pools import (
    PoolCard,
    PoolGrid,
    build_page_footer,
    build_page_heading,
    build_section_title,
)


class HomeView(Gtk.Box):
    def __init__(
        self,
        packs: list[PackSummary],
        db: Database,
        settings: Settings,
        on_open_pool: Callable[[PackSummary], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._packs = packs
        self._db = db
        self._settings = settings
        self._on_open_pool = on_open_pool

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(1000)
        clamp.set_tightening_threshold(500)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(20)
        content.set_margin_bottom(10)
        content.set_margin_start(18)
        content.set_margin_end(18)
        content.set_hexpand(True)

        content.append(
            build_page_heading(
                "Study",
                "Choose a pool to study.",
            )
        )
        content.append(build_section_title("Question Pools"))

        self.grid = PoolGrid(
            packs,
            lambda summary: PoolCard(summary, show_progress=True),
            on_selected=self._on_selected,
            selected_id=settings.active_pool_id,
        )
        content.append(self.grid)

        self.note = Gtk.Label(
            label="Question content is imported from the official NCVEC pools. "
            "FCC rule citations are shown when the pool provides them."
        )
        self.note.add_css_class("dim-label")
        self.note.set_xalign(0)
        self.note.set_wrap(True)
        content.append(self.note)

        clamp.set_child(content)
        scrolled.set_child(clamp)
        self.append(scrolled)

        self.study_button = Gtk.Button(label="Study")
        self.study_button.add_css_class("suggested-action")
        self.study_button.connect("clicked", self._on_study_clicked)
        self.append(build_page_footer(self.study_button))

        self.refresh()

    def _on_selected(self, summary: PackSummary) -> None:
        self._settings.set_active_pool_id(summary.id)

    def _on_study_clicked(self, _button: Gtk.Button) -> None:
        if self.grid.selected is not None:
            self._on_open_pool(self.grid.selected)

    def refresh(self) -> None:
        self.grid.select_id(self._settings.active_pool_id)
        config = self._settings.mastery
        for pack in self._packs:
            seen = self._db.seen_count(pack.id)
            mastered = self._db.mastered_count(pack.id, config)
            self.grid.cards[pack.id].refresh(seen, mastered)


class HomePage(Gtk.Stack):
    def __init__(
        self,
        packs: list[PackSummary],
        db: Database,
        settings: Settings,
        repository: PackRepository,
        on_back_state: Callable[[bool], None],
    ) -> None:
        super().__init__()
        self._on_back_state = on_back_state
        self._repository = repository
        self._home = HomeView(
            packs,
            db,
            settings,
            self._open_pool,
        )
        from .study import StudyView

        self._study = StudyView(db, settings, repository, self.back)
        self.add_named(self._home, "home")
        self.add_named(self._study, "study")
        self.set_visible_child_name("home")

    def _open_pool(self, summary: PackSummary) -> None:
        pack = self._repository.load_pack(summary)
        self._study.start(pack)
        self.set_visible_child_name("study")
        self._on_back_state(True)

    def open_pool(self, pack: Pack) -> None:
        self._open_pool(pack)

    def back(self) -> None:
        self.set_visible_child_name("home")
        self._home.refresh()
        self._on_back_state(False)

    def refresh(self) -> None:
        self._home.refresh()

    @property
    def needs_back(self) -> bool:
        return self.get_visible_child_name() == "study"
