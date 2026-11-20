from __future__ import annotations

from collections.abc import Callable

from gi.repository import Adw, Gtk

from ..data.database import Database
from ..data.packs import PackRepository
from ..domain.models import Pack, is_mastered
from ..settings import Settings


class HomeView(Adw.PreferencesPage):
    def __init__(
        self,
        packs: list[Pack],
        db: Database,
        settings: Settings,
        repository: PackRepository,
        on_open_pool: Callable[[Pack], None],
    ) -> None:
        super().__init__()
        self._packs = packs
        self._db = db
        self._settings = settings
        self._repository = repository
        self._on_open_pool = on_open_pool
        self._progress_labels: dict[str, Gtk.Label] = {}

        group = Adw.PreferencesGroup()
        group.set_title("Question Pools")
        group.set_description(
            "Choose a pool to study. Study mode gives immediate feedback; "
            "practice tests wait until the end."
        )
        self.add(group)

        for pack in packs:
            row = Adw.ActionRow()
            row.set_title(pack.license_name)
            row.set_subtitle(self._subtitle(pack))
            row.set_activatable(True)
            row.set_icon_name("dialog-question-symbolic")

            progress = Gtk.Label()
            progress.add_css_class("dim-label")
            progress.add_css_class("numeric")
            row.add_suffix(progress)
            row.add_suffix(Gtk.Image.new_from_icon_name("go-next-symbolic"))
            row.connect(
                "activated",
                lambda _row, selected=pack: self._on_open_pool(selected),
            )
            group.add(row)
            self._progress_labels[pack.id] = progress

        note = Adw.PreferencesGroup()
        note.set_description(
            "Question content is imported from the official NCVEC pools. "
            "FCC rule citations are shown when the pool provides them. "
            "No explanations are added."
        )
        self.add(note)
        self.refresh()

    def _subtitle(self, pack: Pack) -> str:
        return (
            f"{pack.effective.year}–{pack.expires.year} · "
            f"{len(pack.questions)} questions · Effective "
            f"{pack.effective.strftime('%b %-d, %Y')}"
        )

    def refresh(self) -> None:
        config = self._settings.mastery
        for pack in self._packs:
            progress = self._db.get_progress(pack.id)
            attempted = len(progress)
            mastered = sum(
                1
                for question in pack.questions
                if question.id in progress
                and is_mastered(progress[question.id], config)
            )
            label = self._progress_labels[pack.id]
            label.set_text(f"{attempted} / {len(pack.questions)} seen · {mastered} mastered")


class HomePage(Gtk.Stack):
    def __init__(
        self,
        packs: list[Pack],
        db: Database,
        settings: Settings,
        repository: PackRepository,
        on_back_state: Callable[[bool], None],
    ) -> None:
        super().__init__()
        self._on_back_state = on_back_state
        self._home = HomeView(
            packs,
            db,
            settings,
            repository,
            self._open_pool,
        )
        from .study import StudyView

        self._study = StudyView(db, settings, repository, self.back)
        self.add_named(self._home, "home")
        self.add_named(self._study, "study")
        self.set_visible_child_name("home")

    def _open_pool(self, pack: Pack) -> None:
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
