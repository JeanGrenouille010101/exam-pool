from __future__ import annotations

from collections.abc import Callable

from gi.repository import Adw, Gtk

from ..data.database import Database
from ..data.packs import PackRepository
from ..domain.models import Pack, PackSummary
from ..settings import Settings


class PoolCard(Gtk.Box):
    def __init__(
        self,
        summary: PackSummary,
        on_study: Callable[[PackSummary], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.add_css_class("card")
        self.add_css_class("pool-card")
        self.set_size_request(240, -1)
        self.set_hexpand(True)
        self._summary = summary

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title_box.set_hexpand(True)
        title = Gtk.Label(label=summary.license_name)
        title.add_css_class("title-2")
        title.set_xalign(0)
        title.set_wrap(True)
        title_box.append(title)
        subtitle = Gtk.Label(
            label=f"{summary.effective.year}–{summary.expires.year} · "
            f"{summary.question_count} questions"
        )
        subtitle.add_css_class("dim-label")
        subtitle.set_xalign(0)
        subtitle.set_wrap(True)
        title_box.append(subtitle)
        header.append(title_box)

        self._completion = Gtk.Image.new_from_icon_name("radio-symbolic")
        self._completion.set_pixel_size(20)
        self._completion.set_valign(Gtk.Align.START)
        self._completion.set_tooltip_text("Not all questions seen")
        header.append(self._completion)
        self.append(header)

        self._progress = Gtk.ProgressBar()
        self._progress.set_margin_top(4)
        self.append(self._progress)

        self._progress_label = Gtk.Label()
        self._progress_label.add_css_class("dim-label")
        self._progress_label.set_xalign(0)
        self._progress_label.set_wrap(True)
        self.append(self._progress_label)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_margin_top(4)
        self.study_button = Gtk.Button(label="Study")
        self.study_button.add_css_class("suggested-action")
        self.study_button.set_hexpand(True)
        self.study_button.connect("clicked", lambda _button: on_study(summary))
        actions.append(self.study_button)
        self.append(actions)

        self.refresh(0, 0)

    def refresh(self, seen: int, mastered: int) -> None:
        total = self._summary.question_count
        fraction = seen / total if total else 0.0
        complete = total > 0 and seen >= total
        self._progress.set_fraction(min(1.0, fraction))
        self._progress_label.set_text(
            f"{seen} of {total} seen · {mastered} mastered"
        )
        self._completion.set_from_icon_name(
            "object-select-symbolic" if complete else "radio-symbolic"
        )
        self._completion.set_tooltip_text(
            "All questions seen" if complete else "Not all questions seen"
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
        self._cards: dict[str, PoolCard] = {}

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(1000)
        clamp.set_tightening_threshold(500)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.set_margin_top(28)
        content.set_margin_bottom(32)
        content.set_margin_start(18)
        content.set_margin_end(18)
        content.set_hexpand(True)

        heading = Gtk.Label(label="Question Pools")
        heading.add_css_class("title-1")
        heading.set_xalign(0)
        content.append(heading)
        description = Gtk.Label(
            label="Choose a pool to study. Use the Test tab for a practice test."
        )
        description.add_css_class("dim-label")
        description.set_xalign(0)
        description.set_wrap(True)
        content.append(description)

        rows = []
        for row_index in range((len(packs) + 1) // 2):
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
            row.set_halign(Gtk.Align.CENTER)
            row.set_valign(Gtk.Align.START)
            rows.append(row)
            content.append(row)

        for index, pack in enumerate(packs):
            card = PoolCard(pack, on_open_pool)
            card.set_size_request(300, -1)
            rows[index // 2].append(card)
            self._cards[pack.id] = card
        self.rows = rows

        note = Gtk.Label(
            label="Question content is imported from the official NCVEC pools. "
            "FCC rule citations are shown when the pool provides them."
        )
        note.add_css_class("dim-label")
        note.set_xalign(0)
        note.set_wrap(True)
        note.set_margin_top(6)
        content.append(note)

        clamp.set_child(content)
        scrolled.set_child(clamp)
        self.append(scrolled)
        self.refresh()

    def refresh(self) -> None:
        config = self._settings.mastery
        for pack in self._packs:
            seen = self._db.seen_count(pack.id)
            mastered = self._db.mastered_count(pack.id, config)
            self._cards[pack.id].refresh(seen, mastered)


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
