from __future__ import annotations

from collections.abc import Callable

from gi.repository import Adw, Gtk

from ..data.database import Database
from ..domain.models import Pack
from ..settings import Settings
from .chart import ScoreChart


class StatsView(Adw.PreferencesPage):
    def __init__(
        self,
        packs: list[Pack],
        db: Database,
        settings: Settings,
        on_open_pool: Callable[[Pack], None] | None = None,
    ) -> None:
        super().__init__()
        self._packs = packs
        self._db = db
        self._settings = settings
        self._on_open_pool = on_open_pool
        self._current_pack = self._initial_pack()

        pool_group = Adw.PreferencesGroup()
        pool_group.set_title("Statistics")
        self.add(pool_group)
        self._pool_row = Adw.ComboRow()
        self._pool_row.set_title("Question pool")
        self._pool_row.set_model(
            Gtk.StringList.new([pack.license_name for pack in packs])
        )
        self._pool_row.set_selected(self._packs.index(self._current_pack))
        self._pool_row.connect("notify::selected", self._on_pool_changed)
        pool_group.add(self._pool_row)

        self._overview_group = Adw.PreferencesGroup()
        self._overview_group.set_title("Overview")
        self.add(self._overview_group)
        self._overview_rows: dict[str, Adw.ActionRow] = {}
        for key, title in (
            ("answered", "Questions answered"),
            ("mastered", "Questions mastered"),
            ("unseen", "Questions not answered"),
            ("study_accuracy", "Study accuracy"),
            ("tests", "Practice tests"),
            ("average_score", "Average test score"),
        ):
            row = Adw.ActionRow()
            row.set_title(title)
            self._overview_group.add(row)
            self._overview_rows[key] = row

        chart_group = Adw.PreferencesGroup()
        chart_group.set_title("Practice Test Scores")
        chart_group.set_description(
            "Completed tests, oldest to newest. Timed and untimed tests are included."
        )
        self.add(chart_group)
        chart_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        chart_card.add_css_class("card")
        chart_card.set_margin_top(4)
        chart_card.set_margin_bottom(4)
        self._chart = ScoreChart()
        chart_card.append(self._chart)
        self._chart_caption = Gtk.Label()
        self._chart_caption.add_css_class("dim-label")
        self._chart_caption.set_xalign(0)
        self._chart_caption.set_margin_start(12)
        self._chart_caption.set_margin_end(12)
        self._chart_caption.set_margin_bottom(10)
        chart_card.append(self._chart_caption)
        chart_group.add(chart_card)

        self._group_rows: dict[Adw.PreferencesGroup, list[Gtk.Widget]] = {}
        self._missed_group = Adw.PreferencesGroup()
        self._missed_group.set_title("Most Missed")
        self._missed_group.set_description(
            "Questions with at least three study attempts, ranked by misses."
        )
        self.add(self._missed_group)

        self._correct_group = Adw.PreferencesGroup()
        self._correct_group.set_title("Most Correct")
        self._correct_group.set_description(
            "Questions with at least three study attempts, ranked by correct answers."
        )
        self.add(self._correct_group)

        self.refresh()

    def _initial_pack(self) -> Pack:
        active = self._settings.active_pool_id
        return next((pack for pack in self._packs if pack.id == active), self._packs[0])

    def _on_pool_changed(self, row: Adw.ComboRow, _param) -> None:
        index = row.get_selected()
        if 0 <= index < len(self._packs):
            self._current_pack = self._packs[index]
            self._settings.set_active_pool_id(self._current_pack.id)
            self.refresh()

    def refresh(self, pack: Pack | None = None) -> None:
        if pack is not None:
            self._current_pack = pack
            self._pool_row.set_selected(self._packs.index(pack))
        self._current_pack = next(
            (
                candidate
                for candidate in self._packs
                if candidate.id == self._current_pack.id
            ),
            self._packs[0],
        )
        stats = self._db.get_stats(self._current_pack, self._settings.mastery)
        total = max(1, stats["total"])
        self._set_row(
            "answered",
            f"{stats['attempted']} / {stats['total']} "
            f"({100.0 * stats['attempted'] / total:.0f}%)",
        )
        self._set_row(
            "mastered",
            f"{stats['mastered']} / {stats['total']} "
            f"({100.0 * stats['mastered'] / total:.0f}%)",
        )
        self._set_row("unseen", str(stats["unseen"]))
        self._set_row("study_accuracy", f"{stats['study_accuracy']:.1f}%")
        self._set_row(
            "tests",
            str(stats["tests"]),
        )
        self._set_row(
            "average_score",
            f"{stats['average_score']:.1f}%" if stats["tests"] else "No completed tests",
        )

        history = self._db.score_history(self._current_pack.id)
        self._chart.set_history(history)
        if history:
            self._chart_caption.set_text(
                f"{stats['tests']} completed test"
                f"{'s' if stats['tests'] != 1 else ''} · latest "
                f"{history[-1]['score']:.0f}%"
            )
        else:
            self._chart_caption.set_text("No completed tests yet")

        self._fill_question_group(
            self._missed_group,
            self._db.most_missed(self._current_pack, limit=5, min_attempts=3),
            suffix_key="missed",
            empty="No question has been missed three times yet.",
        )
        self._fill_question_group(
            self._correct_group,
            self._db.most_correct(self._current_pack, limit=5, min_attempts=3),
            suffix_key="times_correct",
            empty="No question has been answered correctly three times yet.",
        )

    def _set_row(self, key: str, value: str) -> None:
        self._overview_rows[key].set_subtitle(value)

    def _fill_question_group(
        self,
        group: Adw.PreferencesGroup,
        rows: list[dict],
        *,
        suffix_key: str,
        empty: str,
    ) -> None:
        old_rows = self._group_rows.pop(group, [])
        for old_row in old_rows:
            group.remove(old_row)
        if not rows:
            row = Adw.ActionRow()
            row.set_title("No data yet")
            row.set_subtitle(empty)
            group.add(row)
            self._group_rows[group] = [row]
            return
        new_rows: list[Gtk.Widget] = []
        for item in rows:
            row = Adw.ActionRow()
            row.set_title(item["question_id"])
            row.set_subtitle(item.get("text") or item["question_id"])
            suffix = Gtk.Label(
                label=f"{item[suffix_key]} / {item['times_asked']}"
            )
            suffix.add_css_class("dim-label")
            suffix.add_css_class("numeric")
            row.add_suffix(suffix)
            if self._on_open_pool is not None:
                row.set_activatable(True)
                row.connect(
                    "activated",
                    lambda _row, pack=self._current_pack: self._on_open_pool(pack),
                )
            group.add(row)
            new_rows.append(row)
        self._group_rows[group] = new_rows
