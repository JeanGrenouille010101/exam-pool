#!/usr/bin/env python3
"""Manual UI smoke test. Run with a Broadway display or a real session."""

from __future__ import annotations

import time
import traceback

from gi.repository import GLib

from exam_pool.application import ExamPoolApplication


def exercise(app: ExamPoolApplication) -> bool:
    try:
        window = app._window
        assert window is not None
        summary = app._summaries[0]
        pack = app._repository.load_pack(summary)
        card = window._home_page._home._cards[summary.id]
        card.test_button.emit("clicked")
        assert window._stack.get_visible_child_name() == "test"
        assert window._test_page._setup._current_pack.id == summary.id
        window._stack.set_visible_child_name("home")
        window._home_page.open_pool(pack)
        study = window._home_page._study
        assert study._current is not None
        assert study._card.has_css_class("question-card")
        question = study._current
        wrong_index = next(
            index
            for index, choice in enumerate(question.choices)
            if choice.id != question.correct
        )
        correct_index = next(
            index
            for index, choice in enumerate(question.choices)
            if choice.id == question.correct
        )
        before_ok, before_bounds = study._action_stack.compute_bounds(window)
        assert before_ok
        study._checks[wrong_index].set_active(True)
        study._on_check_clicked(study._check_button)
        assert study._answered
        after_ok, after_bounds = study._action_stack.compute_bounds(window)
        assert after_ok
        assert abs(before_bounds.get_y() - after_bounds.get_y()) < 1
        assert study._checks[correct_index].has_css_class("correct-answer")
        assert study._checks[wrong_index].has_css_class("wrong-answer")
        study._show_next_question()
        window._home_page.back()

        extra_summary = next(
            item for item in app._summaries if item.license_class == "extra"
        )
        extra = app._repository.load_pack(extra_summary)
        window._home_page.open_pool(extra)
        figure_question = next(q for q in extra.questions if q.figure)
        study._render_figure(figure_question)
        assert study._figure_box.get_first_child() is not None
        window._home_page.back()

        window._stack.set_visible_child_name("test")
        window._test_page._start(pack, False, 30)
        session = window._test_page._session
        assert session._exam
        session._checks[0].set_active(True)
        session._finish()
        assert window._test_page.get_visible_child_name() == "results"

        window._test_page._start(pack, True, 1)
        timed = window._test_page._session
        timed._started = time.monotonic() - 61
        timed._tick()
        assert window._test_page.get_visible_child_name() == "results"

        window._stack.set_visible_child_name("stats")
        window._stats_page.refresh()
        window._stats_page.refresh()

        expected_pages = [("home", "Study"), ("test", "Test"), ("stats", "Stats")]
        for index in range(30):
            name = ("test", "stats", "home", "stats", "test", "home")[index % 6]
            window._stack.set_visible_child_name(name)
            pages = [
                (page.get_name(), page.get_title())
                for page in window._stack.get_pages()
            ]
            assert pages == expected_pages, pages

        window.show_update_banner("Test update banner", action=window.hide_update_banner)
        assert window._banner.get_revealed()
        window.hide_update_banner()
        window.show_preferences()
        window.show_about()
        print("UI smoke test passed")
    except Exception:  # noqa: BLE001 - smoke test must report any failure
        traceback.print_exc()
        return False
    finally:
        app.quit()
    return True


def on_activate(app: ExamPoolApplication) -> None:
    GLib.idle_add(exercise, app)


def main() -> int:
    app = ExamPoolApplication()
    app.connect("activate", on_activate)
    return app.run([])


if __name__ == "__main__":
    raise SystemExit(main())
