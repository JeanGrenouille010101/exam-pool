from __future__ import annotations

from collections.abc import Callable

from gi.repository import Adw, Gtk

from ..settings import Settings
from .dialogs import confirm


class PreferencesDialog(Adw.PreferencesDialog):
    def __init__(
        self,
        settings: Settings,
        parent: Gtk.Widget,
        on_reset: Callable[[], None],
    ) -> None:
        super().__init__()
        self._settings = settings
        self._parent = parent
        self._on_reset = on_reset
        self.set_title("Preferences")
        self.set_search_enabled(False)

        page = Adw.PreferencesPage()
        self.add(page)

        study_group = Adw.PreferencesGroup()
        study_group.set_title("Study")
        page.add(study_group)

        self._attempts = Adw.SpinRow()
        self._attempts.set_title("Minimum attempts")
        self._attempts.set_subtitle(
            "How many times a question is asked before it can be mastered."
        )
        self._attempts.set_adjustment(
            Gtk.Adjustment(
                value=settings.mastery.min_attempts,
                lower=1,
                upper=20,
                step_increment=1,
            )
        )
        study_group.add(self._attempts)

        self._accuracy = Adw.SpinRow()
        self._accuracy.set_title("Mastery accuracy")
        self._accuracy.set_subtitle(
            "Cumulative accuracy required to master a question."
        )
        self._accuracy.set_adjustment(
            Gtk.Adjustment(
                value=round(settings.mastery.target_accuracy * 100),
                lower=1,
                upper=100,
                step_increment=1,
            )
        )
        self._accuracy.set_digits(0)
        accuracy_suffix = Gtk.Label(label="%")
        accuracy_suffix.add_css_class("dim-label")
        self._accuracy.add_suffix(accuracy_suffix)
        study_group.add(self._accuracy)

        self._gap = Adw.SpinRow()
        self._gap.set_title("Missed question gap")
        self._gap.set_subtitle(
            "How many questions to wait before repeating a missed question."
        )
        self._gap.set_adjustment(
            Gtk.Adjustment(
                value=settings.mastery.missed_gap,
                lower=0,
                upper=50,
                step_increment=1,
            )
        )
        study_group.add(self._gap)

        self._references = Adw.SwitchRow()
        self._references.set_title("Show FCC rule references")
        self._references.set_subtitle(
            "Show official citations from the question pool when available."
        )
        self._references.set_active(settings.show_references)
        study_group.add(self._references)

        test_group = Adw.PreferencesGroup()
        test_group.set_title("Tests")
        page.add(test_group)

        self._minutes = Adw.SpinRow()
        self._minutes.set_title("Default timed duration")
        self._minutes.set_subtitle(
            "The FCC does not specify a time limit; this is only a practice default."
        )
        self._minutes.set_adjustment(
            Gtk.Adjustment(
                value=settings.timed_minutes,
                lower=1,
                upper=180,
                step_increment=1,
            )
        )
        minutes_suffix = Gtk.Label(label="min")
        minutes_suffix.add_css_class("dim-label")
        self._minutes.add_suffix(minutes_suffix)
        test_group.add(self._minutes)

        data_group = Adw.PreferencesGroup()
        data_group.set_title("Data")
        page.add(data_group)
        reset_row = Adw.ActionRow()
        reset_row.set_title("Reset all progress")
        reset_row.set_subtitle("Remove study progress and completed test history.")
        reset_button = Gtk.Button(label="Reset")
        reset_button.add_css_class("destructive-action")
        reset_button.set_valign(Gtk.Align.CENTER)
        reset_button.connect("clicked", self._on_reset_clicked)
        reset_row.add_suffix(reset_button)
        data_group.add(reset_row)

        self._attempts.connect("notify::value", self._save)
        self._accuracy.connect("notify::value", self._save)
        self._gap.connect("notify::value", self._save)
        self._minutes.connect("notify::value", self._save)
        self._references.connect("notify::active", self._save)

    def _save(self, *_args) -> None:
        self._settings.set_mastery(
            min_attempts=int(self._attempts.get_value()),
            accuracy=int(self._accuracy.get_value()),
            missed_gap=int(self._gap.get_value()),
        )
        self._settings.set_timed_minutes(int(self._minutes.get_value()))
        self._settings.set_show_references(self._references.get_active())

    def _on_reset_clicked(self, _button: Gtk.Button) -> None:
        confirm(
            self._parent,
            heading="Reset all progress?",
            body="This removes study progress, attempts, and completed test history. It cannot be undone.",
            confirm_label="Reset",
            on_confirm=self._reset,
        )

    def _reset(self) -> None:
        self._on_reset()
        self._settings.set_mastery(min_attempts=3, accuracy=80, missed_gap=5)
        self._attempts.set_value(3)
        self._accuracy.set_value(80)
        self._gap.set_value(5)
