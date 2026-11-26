from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from random import Random

from .models import Pack, Question


class ExamBuildError(ValueError):
    """Raised when a valid exam cannot be built from a pack."""


@dataclass(frozen=True, slots=True)
class ExamQuestion:
    question: Question
    choice_order: tuple[str, ...]

    def ordered_choices(self):
        by_id = {choice.id: choice for choice in self.question.choices}
        return tuple(by_id[choice_id] for choice_id in self.choice_order)


@dataclass(frozen=True, slots=True)
class ExamScore:
    correct: int
    total: int
    passing: int

    @property
    def passed(self) -> bool:
        return self.correct >= self.passing

    @property
    def percentage(self) -> float:
        return 100.0 * self.correct / self.total if self.total else 0.0


def build_exam(pack: Pack, rng: Random | None = None) -> tuple[ExamQuestion, ...]:
    """Build an exam using one question per official syllabus group.

    The NCVEC exam structure is represented by each group's exam_questions
    count. In the current US pools that count is one for every group, giving
    35 questions for Technician/General and 50 for Extra.
    """
    rng = rng or Random()
    by_group = pack.questions_by_group
    selected: list[ExamQuestion] = []

    for group in pack.groups:
        candidates = by_group.get(group.id, ())
        if len(candidates) < group.exam_questions:
            raise ExamBuildError(
                f"group {group.id} has {len(candidates)} questions, "
                f"but {group.exam_questions} are required"
            )
        chosen = rng.sample(list(candidates), k=group.exam_questions)
        for question in chosen:
            selected.append(ExamQuestion(question, question.choice_ids))

    if len(selected) != pack.exam.questions:
        raise ExamBuildError(
            f"generated {len(selected)} questions, expected {pack.exam.questions}"
        )
    return tuple(selected)


def score_exam(
    questions: tuple[ExamQuestion, ...],
    answers: Mapping[str, str],
    passing: int,
) -> ExamScore:
    correct = sum(
        1
        for item in questions
        if answers.get(item.question.id) == item.question.correct
    )
    return ExamScore(correct=correct, total=len(questions), passing=passing)
