from __future__ import annotations

import pytest

from exam_pool.domain.models import (
    MasteryConfig,
    Progress,
    apply_answer,
    is_mastered,
)

CONFIG = MasteryConfig(min_attempts=3, target_accuracy=0.8, missed_gap=5)


def answer(progress: Progress, correct: bool) -> Progress:
    return apply_answer(
        progress,
        correct=correct,
        content_hash="hash-1",
        config=CONFIG,
    ).progress


def test_three_correct_answers_master_a_question() -> None:
    progress = Progress("pack", "T1A01", content_hash="hash-1")
    assert not is_mastered(progress, CONFIG)
    for _ in range(3):
        progress = answer(progress, True)
    assert progress.times_asked == 3
    assert progress.times_correct == 3
    assert is_mastered(progress, CONFIG)


def test_accuracy_is_cumulative_and_last_answer_must_be_correct() -> None:
    progress = Progress("pack", "T1A01", content_hash="hash-1")
    progress = answer(progress, False)
    for _ in range(4):
        progress = answer(progress, True)
    # 4/5 is exactly 80%, and the last answer was correct.
    assert is_mastered(progress, CONFIG)

    progress = answer(progress, False)
    assert progress.times_asked == 6
    assert progress.times_correct == 4
    assert progress.accuracy == pytest.approx(4 / 6)
    assert not is_mastered(progress, CONFIG)


def test_wrong_answer_resets_streak_but_keeps_history() -> None:
    progress = Progress("pack", "T1A01", content_hash="hash-1")
    progress = answer(progress, True)
    progress = answer(progress, True)
    progress = answer(progress, False)
    assert progress.consecutive_correct == 0
    assert progress.consecutive_wrong == 1
    assert progress.times_asked == 3
    assert progress.times_correct == 2


def test_changed_question_content_resets_progress() -> None:
    progress = Progress(
        "pack",
        "T1A01",
        times_asked=10,
        times_correct=9,
        consecutive_correct=9,
        last_result="correct",
        content_hash="old-hash",
    )
    outcome = apply_answer(
        progress,
        correct=True,
        content_hash="new-hash",
        config=CONFIG,
    )
    assert outcome.progress.times_asked == 1
    assert outcome.progress.times_correct == 1
    assert outcome.progress.content_hash == "new-hash"


def test_invalid_mastery_config_is_rejected() -> None:
    with pytest.raises(ValueError):
        MasteryConfig(min_attempts=0)
    with pytest.raises(ValueError):
        MasteryConfig(target_accuracy=1.1)
