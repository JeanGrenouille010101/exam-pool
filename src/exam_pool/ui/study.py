from __future__ import annotations

import time
import uuid
from collections.abc import Callable

from gi.repository import Adw, Gdk, GLib, Gtk

from ..data.database import Database
from ..data.packs import PackRepository
from ..domain.models import Pack, Question, is_mastered
from ..domain.study_queue import StudyQueue
from ..settings import Settings
from .common import clamp_content, reference_text, wrap_label


def clear_box(box: Gtk.Box) -> None:
    child = box.get_first_child()
    while child is not None:
        next_child = child.get_next_sibling()
        box.remove(child)
        child = next_child


class StudyView(Gtk.Box):
    def __init__(
        self,
        db: Database,
        settings: Settings,
        repository: PackRepository,
        on_back: Callable[[], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._db = db
        self._settings = settings
        self._repository = repository
        self._on_back = on_back
        self._pack: Pack | None = None
        self._queue: StudyQueue | None = None
        self._current: Question | None = None
        self._selected: str | None = None
        self._answered = False
        self._session_id = str(uuid.uuid4())
        self._question_started = 0.0
        self._checks: list[Gtk.CheckButton] = []

        self._stack = Gtk.Stack()
        self._stack.set_vexpand(True)
        self.append(self._stack)

        self._question_page = self._build_question_page()
        self._stack.add_named(self._question_page, "question")

        self._status_page = Adw.StatusPage()
        self._stack.add_named(self._status_page, "status")
        self._stack.set_visible_child_name("status")

        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)

    # ------------------------------------------------------------------
    # Construction

    def _build_question_page(self) -> Gtk.Widget:
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(24)
        content.set_margin_bottom(32)
        content.set_margin_start(18)
        content.set_margin_end(18)

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self._pool_title = Gtk.Label()
        self._pool_title.add_css_class("title-2")
        self._pool_title.set_xalign(0)
        header.append(self._pool_title)
        self._session_progress = Gtk.Label()
        self._session_progress.add_css_class("dim-label")
        self._session_progress.set_xalign(0)
        header.append(self._session_progress)
        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_margin_top(4)
        header.append(self._progress_bar)
        content.append(header)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        card.add_css_class("card")
        card.set_margin_top(4)
        self._card = card

        self._question_meta = Gtk.Label()
        self._question_meta.add_css_class("dim-label")
        self._question_meta.add_css_class("caption")
        self._question_meta.set_xalign(0)
        card.append(self._question_meta)

        self._question_label = wrap_label()
        self._question_label.add_css_class("question-text")
        self._question_label.set_selectable(True)
        card.append(self._question_label)

        self._figure_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.append(self._figure_box)

        self._choices_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=6
        )
        self._choices_box.set_margin_top(4)
        card.append(self._choices_box)
        content.append(card)

        self._feedback = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self._feedback.add_css_class("card")
        self._feedback.set_visible(False)
        self._feedback_status = Gtk.Label()
        self._feedback_status.add_css_class("title-4")
        self._feedback_status.set_xalign(0)
        self._feedback.append(self._feedback_status)
        self._feedback_answer = wrap_label()
        self._feedback.append(self._feedback_answer)
        self._feedback_reference = wrap_label()
        self._feedback_reference.add_css_class("dim-label")
        self._feedback.append(self._feedback_reference)
        content.append(self._feedback)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.END)
        self._check_button = Gtk.Button(label="Check answer")
        self._check_button.add_css_class("suggested-action")
        self._check_button.set_sensitive(False)
        self._check_button.connect("clicked", self._on_check_clicked)
        actions.append(self._check_button)

        self._next_button = Gtk.Button(label="Next question")
        self._next_button.add_css_class("suggested-action")
        self._next_button.set_visible(False)
        self._next_button.connect("clicked", self._on_next_clicked)
        actions.append(self._next_button)
        content.append(actions)

        return clamp_content(content)

    # ------------------------------------------------------------------
    # Session lifecycle

    def start(self, pack: Pack) -> None:
        self._pack = pack
        self._queue = StudyQueue.for_pack(
            pack,
            self._db.get_progress(pack.id),
            self._settings.mastery,
        )
        self._session_id = str(uuid.uuid4())
        self._pool_title.set_text(pack.license_name)
        self._show_next_question()

    def _show_next_question(self) -> None:
        assert self._queue is not None
        question = self._queue.next_question()
        if question is None:
            self._show_complete()
            return
        self._current = question
        self._selected = None
        self._answered = False
        self._question_started = time.monotonic()

        self._question_meta.set_text(
            f"{question.id} · {self._pack.group_name(question.group)}"
        )
        self._question_label.set_text(question.text)
        self._render_figure(question)
        self._render_choices(question)
        self._feedback.set_visible(False)
        self._check_button.set_visible(True)
        self._check_button.set_sensitive(False)
        self._next_button.set_visible(False)
        self._stack.set_visible_child_name("question")
        self._update_progress()

    def _render_figure(self, question: Question) -> None:
        clear_box(self._figure_box)
        if not question.figure:
            self._figure_box.set_visible(False)
            return
        path = self._repository.figure_path(question.figure)
        if path is None:
            label = Gtk.Label(label=f"Figure {question.figure} is unavailable")
            label.add_css_class("dim-label")
            self._figure_box.append(label)
            self._figure_box.set_visible(True)
            return

        try:
            picture = Gtk.Picture.new_for_filename(str(path))
            picture.set_can_shrink(True)
            picture.set_halign(Gtk.Align.CENTER)
            picture.set_margin_top(4)
            picture.set_margin_bottom(4)
            self._figure_box.append(picture)
            self._figure_box.set_visible(True)
        except GLib.Error:
            label = Gtk.Label(label=f"Could not load Figure {question.figure}")
            label.add_css_class("dim-label")
            self._figure_box.append(label)
            self._figure_box.set_visible(True)

    def _render_choices(self, question: Question) -> None:
        clear_box(self._choices_box)
        self._checks = []
        first: Gtk.CheckButton | None = None
        for choice in question.choices:
            check = Gtk.CheckButton()
            label = Gtk.Label(label=f"{choice.id}. {choice.text}")
            label.set_wrap(True)
            label.set_xalign(0)
            check.set_child(label)
            check.set_halign(Gtk.Align.FILL)
            check.add_css_class("answer-choice")
            if first is None:
                first = check
            else:
                check.set_group(first)
            check.connect("toggled", self._on_choice_toggled, choice.id)
            self._choices_box.append(check)
            self._checks.append(check)

    def _show_complete(self) -> None:
        self._current = None
        self._feedback.set_visible(False)
        self._check_button.set_visible(False)
        self._next_button.set_visible(False)
        assert self._pack is not None
        progress = self._db.get_progress(self._pack.id)
        config = self._settings.mastery
        mastered = sum(
            1
            for question in self._pack.questions
            if question.id in progress
            and is_mastered(progress[question.id], config)
        )
        all_mastered = mastered == len(self._pack.questions)
        self._status_page.set_icon_name(
            "emblem-ok-symbolic" if all_mastered else "view-refresh-symbolic"
        )
        if all_mastered:
            self._status_page.set_title("All caught up")
            self._status_page.set_description(
                "You have mastered every question in this pool. "
                "You can return to the pool list or take a practice test."
            )
        else:
            self._status_page.set_title("Session complete")
            self._status_page.set_description(
                f"You have mastered {mastered} of {len(self._pack.questions)} "
                "questions in this pool. Study again to build more mastery."
            )
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.set_halign(Gtk.Align.CENTER)
        if not all_mastered:
            study_again = Gtk.Button(label="Study again")
            study_again.add_css_class("suggested-action")
            study_again.connect(
                "clicked",
                lambda _button: self.start(self._pack) if self._pack else None,
            )
            buttons.append(study_again)
        back = Gtk.Button(label="Back to pools")
        back.connect("clicked", lambda _button: self._on_back())
        buttons.append(back)
        self._status_page.set_child(buttons)
        self._stack.set_visible_child_name("status")
        self._update_progress()

    # ------------------------------------------------------------------
    # Answer flow

    def _on_choice_toggled(self, check: Gtk.CheckButton, choice_id: str) -> None:
        if check.get_active():
            self._selected = choice_id
            self._check_button.set_sensitive(True)

    def _on_check_clicked(self, _button: Gtk.Button) -> None:
        self._submit_answer()

    def _submit_answer(self) -> None:
        if self._answered or self._selected is None:
            return
        assert self._queue is not None
        assert self._pack is not None
        assert self._current is not None

        response_ms = int((time.monotonic() - self._question_started) * 1000)
        outcome = self._db.record_study_answer(
            self._pack,
            self._current,
            self._selected,
            self._settings.mastery,
            session_id=self._session_id,
            response_ms=response_ms,
        )
        self._queue.submit(outcome.correct, outcome.progress)
        self._answered = True

        for check in self._checks:
            check.set_sensitive(False)
        self._check_button.set_visible(False)
        self._feedback.set_visible(True)
        self._feedback.remove_css_class("success")
        self._feedback.remove_css_class("error")
        self._feedback.add_css_class("success" if outcome.correct else "error")
        self._feedback_status.set_text("Correct" if outcome.correct else "Incorrect")
        self._feedback_status.remove_css_class("success")
        self._feedback_status.remove_css_class("error")
        self._feedback_status.add_css_class(
            "success" if outcome.correct else "error"
        )
        correct_choice = next(
            choice
            for choice in self._current.choices
            if choice.id == self._current.correct
        )
        self._feedback_answer.set_text(
            f"Correct answer: {correct_choice.id}. {correct_choice.text}"
        )
        reference = (
            reference_text(self._current.reference)
            if self._settings.show_references
            else None
        )
        self._feedback_reference.set_text(reference or "")
        self._feedback_reference.set_visible(bool(reference))
        self._next_button.set_visible(True)
        self._next_button.set_label(
            "Finish" if self._queue.finished else "Next question"
        )
        self._next_button.grab_focus()
        self._update_progress()

    def _on_next_clicked(self, _button: Gtk.Button) -> None:
        self._show_next_question()

    def _update_progress(self) -> None:
        if self._queue is None:
            return
        answered = self._queue.answered
        remaining = self._queue.remaining
        total = max(1, answered + remaining)
        self._session_progress.set_text(
            f"{answered} answered · {remaining} queued"
        )
        self._progress_bar.set_fraction(min(1.0, answered / total))

    # ------------------------------------------------------------------
    # Keyboard

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        if self._stack.get_visible_child_name() != "question":
            return False
        if keyval in (Gdk.KEY_1, Gdk.KEY_KP_1):
            index = 0
        elif keyval in (Gdk.KEY_2, Gdk.KEY_KP_2):
            index = 1
        elif keyval in (Gdk.KEY_3, Gdk.KEY_KP_3):
            index = 2
        elif keyval in (Gdk.KEY_4, Gdk.KEY_KP_4):
            index = 3
        else:
            index = -1
        if index >= 0 and not self._answered and index < len(self._checks):
            self._checks[index].set_active(True)
            return True
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self._answered:
                self._show_next_question()
            elif self._selected is not None:
                self._submit_answer()
            return True
        return False
