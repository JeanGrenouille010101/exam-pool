#!/usr/bin/env python3
"""Regression check for the non-wrapping question metadata layout bug."""

from __future__ import annotations

import sys

from gi.repository import GLib

from exam_pool.application import ExamPoolApplication


def find_controls(widget, found):
    if type(widget).__name__ == "WindowControls" and widget.get_width() > 0:
        found.append(widget)
    child = widget.get_first_child()
    while child is not None:
        find_controls(child, found)
        child = child.get_next_sibling()


def run_checks(app: ExamPoolApplication, state: dict[str, bool]) -> bool:
    window = app._window
    assert window is not None
    summary = max(
        app._summaries,
        key=lambda item: item.question_count,
    )
    pack = app._repository.load_pack(summary)
    question = max(
        pack.questions,
        key=lambda item: len(pack.group_name(item.group)),
    )

    window._home_page.open_pool(pack)
    study = window._home_page._study
    study._current = question
    study._set_question_meta(question)
    study._question_label.set_text(question.text)
    study._render_figure(question)
    study._render_choices(question)
    study._stack.set_visible_child_name("question")

    def measure() -> bool:
        try:
            minimum, natural = window.get_preferred_size()
            print(
                f"window={window.get_width()}x{window.get_height()} "
                f"study={study.get_width()}x{study.get_height()} "
                f"meta={study._question_meta.get_width()} "
                f"minimum={minimum.width} natural={natural.width}"
            )
            assert natural.width <= 1000, (
                f"window natural width regressed to {natural.width}px"
            )
            assert study.get_width() <= window.get_width() + 2, (
                f"study view is {study.get_width()}px in a "
                f"{window.get_width()}px window"
            )
            ok, bounds = study._check_button.compute_bounds(window)
            assert ok, "could not compute Check answer bounds"
            right = bounds.get_x() + bounds.get_width()
            assert right <= window.get_width() + 2, (
                f"Check answer right edge is {right}px in a "
                f"{window.get_width()}px window"
            )

            controls = []
            find_controls(window._header, controls)
            assert controls, "window controls were not found"
            control = controls[0]
            ok, bounds = control.compute_bounds(window)
            assert ok, "could not compute window controls bounds"
            control_right = bounds.get_x() + bounds.get_width()
            assert control_right <= window.get_width() + 2, (
                f"window controls right edge is {control_right}px in a "
                f"{window.get_width()}px window"
            )
            print("scale smoke test passed")
            state["ok"] = True
            return True
        except AssertionError as exc:
            print(f"scale smoke test failed: {exc}", file=sys.stderr)
            return False
        finally:
            app.quit()

    GLib.timeout_add(800, measure)
    return False


def main() -> int:
    app = ExamPoolApplication()
    state = {"ok": False}
    app.connect(
        "activate",
        lambda application: GLib.timeout_add(
            100, run_checks, application, state
        ),
    )
    app.run([])
    return 0 if state["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
