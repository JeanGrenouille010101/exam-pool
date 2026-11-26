from __future__ import annotations

from random import Random

from exam_pool.domain.exam import build_exam, score_exam


def test_exam_uses_one_question_per_group(pack) -> None:
    exam = build_exam(pack, Random(7))
    assert len(exam) == pack.exam.questions
    selected_groups = [item.question.group for item in exam]
    assert sorted(selected_groups) == sorted(group.id for group in pack.groups)
    for item in exam:
        assert item.choice_order == item.question.choice_ids


def test_exam_generation_is_deterministic_with_seed(pack) -> None:
    first = build_exam(pack, Random(42))
    second = build_exam(pack, Random(42))
    assert [item.question.id for item in first] == [
        item.question.id for item in second
    ]
    assert [item.choice_order for item in first] == [
        item.choice_order for item in second
    ]


def test_exam_scoring(pack) -> None:
    exam = build_exam(pack, Random(3))
    answers = {item.question.id: item.question.correct for item in exam[:-1]}
    answers[exam[-1].question.id] = next(
        choice_id
        for choice_id in exam[-1].question.choice_ids
        if choice_id != exam[-1].question.correct
    )
    score = score_exam(exam, answers, pack.exam.passing)
    assert score.correct == 3
    assert score.total == 4
    assert score.passed
    assert score.percentage == 75.0
