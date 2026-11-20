from __future__ import annotations

import time
from collections.abc import Callable

from gi.repository import Adw, Gdk, GLib, Gtk

from ..data.database import Database, utc_now
from ..data.packs import PackRepository
from ..domain.exam import ExamQuestion, build_exam
from ..domain.models import Pack
from ..settings import Settings
from .common import clamp_content, reference_text, wrap_label
from .dialogs import confirm
from .study import clear_box


def format_duration(seconds: int | None) -> str:
    if seconds is None:
        return "Untimed"
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


class TestSetupView(Adw.PreferencesPage):
    def __init__(
        self,
        packs: list[Pack],
        settings: Settings,
        on_start: Callable[[Pack, bool, int], None],
    ) -> None:
        super().__init__()
        self._packs = packs
        self._settings = settings
        self._on_start = on_start
        self._current_pack = self._initial_pack()

        group = Adw.PreferencesGroup()
        group.set_title("Practice Test")
        group.set_description(
            "Tests use one question from each official syllabus group and "
            "show all feedback only after submission."
        )
        self.add(group)

        self._pool_row = Adw.ComboRow()
        self._pool_row.set_title("Question pool")
        names = Gtk.StringList.new([pack.license_name for pack in packs])
        self._pool_row.set_model(names)
        self._pool_row.set_selected(self._pack_index())
        self._pool_row.connect("notify::selected", self._on_pool_changed)
        group.add(self._pool_row)

        self._summary_row = Adw.ActionRow()
        self._summary_row.set_title("Exam")
        group.add(self._summary_row)

        self._timed_row = Adw.SwitchRow()
        self._timed_row.set_title("Timed test")
        self._timed_row.set_subtitle(
            "The FCC does not set a time limit for these exams; choose your own practice duration."
        )
        self._timed_row.set_active(False)
        self._timed_row.connect("notify::active", self._on_timed_changed)
        group.add(self._timed_row)

        self._minutes_row = Adw.SpinRow()
        self._minutes_row.set_title("Minutes")
        adjustment = Gtk.Adjustment(
            value=settings.timed_minutes,
            lower=1,
            upper=180,
            step_increment=1,
            page_increment=5,
        )
        self._minutes_row.set_adjustment(adjustment)
        self._minutes_row.set_visible(False)
        self._minutes_row.set_sensitive(False)
        group.add(self._minutes_row)

        start_group = Adw.PreferencesGroup()
        start_button = Gtk.Button(label="Start Test")
        start_button.add_css_class("suggested-action")
        start_button.add_css_class("pill")
        start_button.set_halign(Gtk.Align.CENTER)
        start_button.set_margin_top(12)
        start_button.set_margin_bottom(12)
        start_button.connect("clicked", self._on_start_clicked)
        start_group.add(start_button)
        self.add(start_group)

        self._refresh_summary()

    def _initial_pack(self) -> Pack:
        active = self._settings.active_pool_id
        return next((pack for pack in self._packs if pack.id == active), self._packs[0])

    def _pack_index(self) -> int:
        return self._packs.index(self._current_pack)

    def _on_pool_changed(self, row: Adw.ComboRow, _param) -> None:
        index = row.get_selected()
        if 0 <= index < len(self._packs):
            self._current_pack = self._packs[index]
            self._settings.set_active_pool_id(self._current_pack.id)
            self._refresh_summary()

    def _refresh_summary(self) -> None:
        pack = self._current_pack
        self._summary_row.set_subtitle(
            f"{pack.exam.questions} questions · "
            f"{pack.exam.passing} correct to pass · "
            f"{pack.effective.year}–{pack.expires.year} pool"
        )

    def _on_timed_changed(self, row: Adw.SwitchRow, _param) -> None:
        timed = row.get_active()
        self._minutes_row.set_visible(timed)
        self._minutes_row.set_sensitive(timed)

    def _on_start_clicked(self, _button: Gtk.Button) -> None:
        timed = self._timed_row.get_active()
        minutes = int(self._minutes_row.get_value())
        self._on_start(self._current_pack, timed, minutes)


class TestSessionView(Gtk.Box):
    def __init__(
        self,
        db: Database,
        repository: PackRepository,
        on_finished: Callable[[str, int], None],
        on_request_back: Callable[[], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._db = db
        self._repository = repository
        self._on_finished = on_finished
        self._on_request_back = on_request_back
        self._session_id: str | None = None
        self._pack: Pack | None = None
        self._exam: tuple[ExamQuestion, ...] = ()
        self._index = 0
        self._answers: dict[str, str] = {}
        self._checks: list[Gtk.CheckButton] = []
        self._timer_id: int | None = None
        self._started = 0.0
        self._time_limit: int | None = None
        self._finished = False

        self._stack = Gtk.Stack()
        self._stack.set_vexpand(True)
        self.append(self._stack)
        self._question_page = self._build_question_page()
        self._stack.add_named(self._question_page, "question")

        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_pressed)
        self.add_controller(key_controller)

    def _build_question_page(self) -> Gtk.Widget:
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        content.set_margin_top(24)
        content.set_margin_bottom(32)
        content.set_margin_start(18)
        content.set_margin_end(18)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        top.set_valign(Gtk.Align.CENTER)
        self._pool_title = Gtk.Label()
        self._pool_title.add_css_class("title-2")
        self._pool_title.set_xalign(0)
        self._pool_title.set_hexpand(True)
        top.append(self._pool_title)
        self._timer_label = Gtk.Label()
        self._timer_label.add_css_class("title-4")
        self._timer_label.add_css_class("numeric")
        self._timer_label.set_visible(False)
        top.append(self._timer_label)
        content.append(top)

        self._progress_label = Gtk.Label()
        self._progress_label.add_css_class("dim-label")
        self._progress_label.set_xalign(0)
        content.append(self._progress_label)
        self._progress_bar = Gtk.ProgressBar()
        content.append(self._progress_bar)

        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        card.add_css_class("card")
        self._question_meta = Gtk.Label()
        self._question_meta.add_css_class("dim-label")
        self._question_meta.add_css_class("caption")
        self._question_meta.set_xalign(0)
        card.append(self._question_meta)
        self._question_label = wrap_label()
        self._question_label.add_css_class("question-text")
        card.append(self._question_label)
        self._figure_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.append(self._figure_box)
        self._choices_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=6
        )
        self._choices_box.set_margin_top(4)
        card.append(self._choices_box)
        content.append(card)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.CENTER)
        self._previous_button = Gtk.Button(label="Previous")
        self._previous_button.connect("clicked", self._on_previous)
        actions.append(self._previous_button)
        self._next_button = Gtk.Button(label="Next")
        self._next_button.connect("clicked", self._on_next)
        actions.append(self._next_button)
        self._submit_button = Gtk.Button(label="Submit Test")
        self._submit_button.add_css_class("suggested-action")
        self._submit_button.connect("clicked", self._on_submit)
        actions.append(self._submit_button)
        content.append(actions)

        return clamp_content(content, maximum_size=820)

    # ------------------------------------------------------------------

    def start(
        self,
        session_id: str,
        pack: Pack,
        exam: tuple[ExamQuestion, ...],
        *,
        mode: str,
        time_limit_seconds: int | None,
    ) -> None:
        self._session_id = session_id
        self._pack = pack
        self._exam = exam
        self._index = 0
        self._answers = {
            exam[position].question.id: selected
            for position, selected in self._db.get_test_answers(session_id).items()
        }
        self._time_limit = time_limit_seconds
        self._started = time.monotonic()
        self._finished = False
        self._pool_title.set_text(pack.license_name)
        self._timer_label.set_visible(mode == "timed")
        self._show_question()
        if mode == "timed":
            self.stop()
            self._tick()
            if not self._finished:
                self._timer_id = GLib.timeout_add_seconds(1, self._tick)

    def stop(self) -> None:
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None

    def _show_question(self) -> None:
        if not self._pack or not self._exam:
            return
        item = self._exam[self._index]
        question = item.question
        self._question_meta.set_text(
            f"{question.id} · {self._pack.group_name(question.group)}"
        )
        self._question_label.set_text(question.text)
        self._render_figure(question)
        self._render_choices(item)
        self._progress_label.set_text(
            f"Question {self._index + 1} of {len(self._exam)}"
        )
        self._progress_bar.set_fraction((self._index + 1) / len(self._exam))
        self._previous_button.set_sensitive(self._index > 0)
        self._next_button.set_sensitive(self._index < len(self._exam) - 1)
        self._next_button.set_visible(self._index < len(self._exam) - 1)
        self._submit_button.set_visible(self._index == len(self._exam) - 1)

    def _render_figure(self, question) -> None:
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

    def _render_choices(self, item: ExamQuestion) -> None:
        clear_box(self._choices_box)
        self._checks = []
        by_id = {choice.id: choice for choice in item.question.choices}
        selected = self._answers.get(item.question.id)
        first: Gtk.CheckButton | None = None
        for choice_id in item.choice_order:
            choice = by_id[choice_id]
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
            check.set_active(choice.id == selected)
            check.connect("toggled", self._on_choice_toggled, item.question.id, choice.id)
            self._choices_box.append(check)
            self._checks.append(check)

    def _on_choice_toggled(
        self,
        check: Gtk.CheckButton,
        question_id: str,
        choice_id: str,
    ) -> None:
        if not check.get_active() or not self._session_id:
            return
        self._answers[question_id] = choice_id
        if self._pack:
            question = self._pack.question_map[question_id]
            self._db.save_test_answer(
                self._session_id, self._index, question, choice_id
            )

    def _save_current(self) -> None:
        if not self._session_id or not self._pack or not self._exam:
            return
        item = self._exam[self._index]
        selected = self._answers.get(item.question.id)
        self._db.save_test_answer(
            self._session_id, self._index, item.question, selected
        )

    def _on_previous(self, _button: Gtk.Button) -> None:
        self._save_current()
        if self._index > 0:
            self._index -= 1
            self._show_question()

    def _on_next(self, _button: Gtk.Button) -> None:
        self._save_current()
        if self._index < len(self._exam) - 1:
            self._index += 1
            self._show_question()

    def _on_submit(self, _button: Gtk.Button) -> None:
        self._save_current()
        unanswered = sum(
            1
            for item in self._exam
            if item.question.id not in self._answers
        )
        if unanswered:
            confirm(
                self.get_root(),
                heading="Submit test?",
                body=f"{unanswered} question{'s' if unanswered != 1 else ''} "
                "have not been answered. They will be marked incorrect.",
                confirm_label="Submit",
                on_confirm=self._finish,
            )
        else:
            self._finish()

    def _finish(self) -> None:
        if self._finished or not self._session_id:
            return
        self._finished = True
        self.stop()
        self._save_current()
        elapsed = int(time.monotonic() - self._started)
        self._db.finish_test_session(
            self._session_id,
            elapsed_seconds=elapsed,
        )
        self._on_finished(self._session_id, elapsed)

    def _tick(self) -> bool:
        if self._finished:
            return GLib.SOURCE_REMOVE
        if self._time_limit is None:
            self._timer_label.set_visible(False)
            return GLib.SOURCE_CONTINUE
        remaining = self._time_limit - int(time.monotonic() - self._started)
        if remaining <= 0:
            self._timer_label.set_text("0:00")
            self._timer_label.add_css_class("error")
            self._timer_id = None
            self._finish()
            return GLib.SOURCE_REMOVE
        self._timer_label.set_text(format_duration(remaining))
        if remaining <= 60:
            self._timer_label.add_css_class("error")
        else:
            self._timer_label.remove_css_class("error")
        return GLib.SOURCE_CONTINUE

    def _on_key_pressed(
        self,
        _controller: Gtk.EventControllerKey,
        keyval: int,
        _keycode: int,
        _state: Gdk.ModifierType,
    ) -> bool:
        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self._index < len(self._exam) - 1:
                self._on_next(self._next_button)
            else:
                self._on_submit(self._submit_button)
            return True
        return False


class TestResultsView(Gtk.Box):
    def __init__(self, on_back: Callable[[], None]) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self._on_back = on_back
        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self._content.set_margin_top(24)
        self._content.set_margin_bottom(32)
        self._content.set_margin_start(18)
        self._content.set_margin_end(18)
        self._status = Adw.StatusPage()
        self._content.append(self._status)
        self._groups = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self._content.append(self._groups)
        self.append(clamp_content(self._content, maximum_size=820))

    def show_result(
        self,
        pack: Pack,
        exam: tuple[ExamQuestion, ...],
        result: dict,
        *,
        answers: dict[str, str],
        mode: str,
        time_limit_seconds: int | None,
        elapsed_seconds: int,
    ) -> None:
        passed = bool(result["passed"])
        self._status.set_icon_name(
            "emblem-ok-symbolic" if passed else "dialog-error-symbolic"
        )
        self._status.set_title("Passed" if passed else "Not passed")
        percentage = 100.0 * result["correct"] / result["total"]
        self._status.set_description(
            f"{result['correct']} of {result['total']} correct "
            f"({percentage:.0f}%). Passing score: {result['passing']}."
        )
        button = Gtk.Button(label="Back to tests")
        button.add_css_class("suggested-action")
        button.set_halign(Gtk.Align.CENTER)
        button.connect("clicked", lambda _button: self._on_back())
        self._status.set_child(button)

        child = self._groups.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._groups.remove(child)
            child = next_child

        summary = Adw.PreferencesGroup()
        summary.set_title("Result")
        score_row = Adw.ActionRow()
        score_row.set_title("Score")
        score_row.set_subtitle(f"{result['correct']} / {result['total']}")
        summary.add(score_row)
        mode_row = Adw.ActionRow()
        mode_row.set_title("Mode")
        mode_row.set_subtitle(
            f"Timed · {format_duration(time_limit_seconds)}"
            if mode == "timed"
            else "Untimed"
        )
        summary.add(mode_row)
        time_row = Adw.ActionRow()
        time_row.set_title("Time used")
        time_row.set_subtitle(format_duration(elapsed_seconds))
        summary.add(time_row)
        self._groups.append(summary)

        review_group = Adw.PreferencesGroup()
        review_group.set_title("Review")
        review_group.set_description(
            "Correct answers and official references only; no explanations."
        )
        for item in exam:
            question = item.question
            selected = answers.get(question.id)
            row = Adw.ExpanderRow()
            row.set_title(
                f"{question.id} · {'Correct' if selected == question.correct else 'Incorrect'}"
            )
            row.set_subtitle(question.text)
            your_answer = Adw.ActionRow()
            your_answer.set_title("Your answer")
            your_answer.set_subtitle(
                "Not answered"
                if selected is None
                else f"{selected}. {question.choice_text(selected)}"
            )
            row.add_row(your_answer)
            correct = Adw.ActionRow()
            correct.set_title("Correct answer")
            correct.set_subtitle(
                f"{question.correct}. {question.choice_text(question.correct)}"
            )
            row.add_row(correct)
            reference = reference_text(question.reference)
            if reference:
                ref_row = Adw.ActionRow()
                ref_row.set_title("Reference")
                ref_row.set_subtitle(reference)
                row.add_row(ref_row)
            review_group.add(row)
        self._groups.append(review_group)


class TestPage(Gtk.Stack):
    def __init__(
        self,
        packs: list[Pack],
        db: Database,
        settings: Settings,
        repository: PackRepository,
        on_back_state: Callable[[bool], None],
    ) -> None:
        super().__init__()
        self._packs = packs
        self._db = db
        self._settings = settings
        self._repository = repository
        self._on_back_state = on_back_state
        self._active_session: str | None = None
        self._active_pack: Pack | None = None
        self._active_exam: tuple[ExamQuestion, ...] = ()
        self._active_mode = "untimed"
        self._active_limit: int | None = None

        self._setup = TestSetupView(packs, settings, self._start)
        self._session = TestSessionView(
            db,
            repository,
            self._finished,
            self.request_back,
        )
        self._results = TestResultsView(self.show_setup)
        self.add_named(self._setup, "setup")
        self.add_named(self._session, "session")
        self.add_named(self._results, "results")
        self.set_visible_child_name("setup")

    def _start(self, pack: Pack, timed: bool, minutes: int) -> None:
        mode = "timed" if timed else "untimed"
        limit = minutes * 60 if timed else None
        exam = build_exam(pack)
        session_id = self._db.start_test_session(
            pack,
            mode=mode,
            time_limit_seconds=limit,
            exam=exam,
        )
        self._active_session = session_id
        self._active_pack = pack
        self._active_exam = exam
        self._active_mode = mode
        self._active_limit = limit
        self._session.start(
            session_id,
            pack,
            exam,
            mode=mode,
            time_limit_seconds=limit,
        )
        self.set_visible_child_name("session")
        self._on_back_state(True)

    def _finished(self, session_id: str, elapsed: int) -> None:
        if self._active_pack is None:
            return
        row = self._db.get_test_session(session_id)
        result = {
            "correct": int(row["correct_count"] or 0),
            "total": int(row["total_questions"]),
            "passing": int(row["passing"]),
            "passed": bool(row["passed"]),
        }
        answers = {
            self._active_exam[position].question.id: selected
            for position, selected in self._db.get_test_answers(session_id).items()
        }
        self._results.show_result(
            self._active_pack,
            self._active_exam,
            result,
            answers=answers,
            mode=self._active_mode,
            time_limit_seconds=self._active_limit,
            elapsed_seconds=elapsed,
        )
        self._active_session = None
        self.set_visible_child_name("results")
        self._on_back_state(False)

    def show_setup(self) -> None:
        self._session.stop()
        if self._active_session:
            self._db.abandon_test_session(self._active_session)
            self._active_session = None
        self.set_visible_child_name("setup")
        self._on_back_state(False)

    def shutdown(self) -> None:
        self._session.stop()
        if self._active_session:
            self._db.abandon_test_session(self._active_session)
            self._active_session = None

    def request_back(self) -> None:
        if self.get_visible_child_name() != "session" or not self._active_session:
            self.show_setup()
            return
        confirm(
            self.get_root(),
            heading="Leave this test?",
            body="The test will be abandoned and its answers will not count toward your statistics.",
            confirm_label="Leave Test",
            on_confirm=self._abandon,
        )

    def _abandon(self) -> None:
        if self._active_session:
            self._db.abandon_test_session(self._active_session)
            self._active_session = None
        self._session.stop()
        self.show_setup()

    def refresh(self) -> None:
        self._setup._refresh_summary()
