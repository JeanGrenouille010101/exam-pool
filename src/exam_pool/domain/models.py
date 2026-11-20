from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Any


class PackError(ValueError):
    """Raised when a question pack is malformed."""


@dataclass(frozen=True, slots=True)
class Choice:
    id: str
    text: str


@dataclass(frozen=True, slots=True)
class Question:
    id: str
    group: str
    text: str
    choices: tuple[Choice, ...]
    correct: str
    reference: str | None = None
    figure: str | None = None

    @property
    def choice_ids(self) -> tuple[str, ...]:
        return tuple(choice.id for choice in self.choices)

    def choice_text(self, choice_id: str) -> str:
        for choice in self.choices:
            if choice.id == choice_id:
                return choice.text
        raise KeyError(choice_id)

    @property
    def content_hash(self) -> str:
        payload = {
            "id": self.id,
            "group": self.group,
            "text": self.text,
            "choices": [(choice.id, choice.text) for choice in self.choices],
            "correct": self.correct,
            "reference": self.reference,
            "figure": self.figure,
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class Group:
    id: str
    name: str
    subelement: str
    exam_questions: int


@dataclass(frozen=True, slots=True)
class ExamRules:
    questions: int
    passing: int


@dataclass(frozen=True, slots=True)
class Source:
    name: str
    url: str
    revision: str
    license: str


@dataclass(frozen=True, slots=True)
class Pack:
    schema: int
    id: str
    country: str
    country_name: str
    license_class: str
    license_name: str
    element: int
    effective: date
    expires: date
    source: Source
    exam: ExamRules
    groups: tuple[Group, ...]
    questions: tuple[Question, ...]

    @property
    def group_map(self) -> dict[str, Group]:
        return {group.id: group for group in self.groups}

    @property
    def question_map(self) -> dict[str, Question]:
        return {question.id: question for question in self.questions}

    @property
    def questions_by_group(self) -> dict[str, tuple[Question, ...]]:
        result: dict[str, list[Question]] = {group.id: [] for group in self.groups}
        for question in self.questions:
            result.setdefault(question.group, []).append(question)
        return {group_id: tuple(items) for group_id, items in result.items()}

    def group_name(self, group_id: str) -> str:
        group = self.group_map.get(group_id)
        return group.name if group else group_id


@dataclass(frozen=True, slots=True)
class PackSummary:
    id: str
    country: str
    country_name: str
    license_class: str
    license_name: str
    element: int
    effective: date
    expires: date
    source: Source
    exam: ExamRules
    question_count: int
    group_count: int


@dataclass(frozen=True, slots=True)
class Progress:
    pack_id: str
    question_id: str
    times_asked: int = 0
    times_correct: int = 0
    consecutive_correct: int = 0
    consecutive_wrong: int = 0
    last_result: str | None = None
    content_hash: str = ""

    @property
    def accuracy(self) -> float:
        if self.times_asked == 0:
            return 0.0
        return self.times_correct / self.times_asked

    @property
    def missed(self) -> int:
        return self.times_asked - self.times_correct


@dataclass(frozen=True, slots=True)
class AnswerOutcome:
    progress: Progress
    correct: bool
    was_mastered: bool
    now_mastered: bool


@dataclass(frozen=True, slots=True)
class MasteryConfig:
    min_attempts: int = 3
    target_accuracy: float = 0.80
    missed_gap: int = 5

    def __post_init__(self) -> None:
        if self.min_attempts < 1:
            raise ValueError("min_attempts must be at least 1")
        if not 0.0 <= self.target_accuracy <= 1.0:
            raise ValueError("target_accuracy must be between 0 and 1")
        if self.missed_gap < 0:
            raise ValueError("missed_gap cannot be negative")



def question_meta_text(question: Question) -> str:
    """Short, layout-safe metadata for a question row."""
    return f"{question.id} · {question.group}"

def is_mastered(progress: Progress, config: MasteryConfig) -> bool:
    return (
        progress.times_asked >= config.min_attempts
        and progress.accuracy >= config.target_accuracy
        and progress.last_result == "correct"
    )


def apply_answer(
    progress: Progress,
    *,
    correct: bool,
    content_hash: str,
    config: MasteryConfig,
) -> AnswerOutcome:
    """Apply one answer, resetting history if the question content changed."""
    if progress.content_hash and progress.content_hash != content_hash:
        progress = Progress(
            pack_id=progress.pack_id,
            question_id=progress.question_id,
            content_hash=content_hash,
        )

    was_mastered = is_mastered(progress, config)
    if correct:
        progress = Progress(
            pack_id=progress.pack_id,
            question_id=progress.question_id,
            times_asked=progress.times_asked + 1,
            times_correct=progress.times_correct + 1,
            consecutive_correct=progress.consecutive_correct + 1,
            consecutive_wrong=0,
            last_result="correct",
            content_hash=content_hash,
        )
    else:
        progress = Progress(
            pack_id=progress.pack_id,
            question_id=progress.question_id,
            times_asked=progress.times_asked + 1,
            times_correct=progress.times_correct,
            consecutive_correct=0,
            consecutive_wrong=progress.consecutive_wrong + 1,
            last_result="wrong",
            content_hash=content_hash,
        )

    return AnswerOutcome(
        progress=progress,
        correct=correct,
        was_mastered=was_mastered,
        now_mastered=is_mastered(progress, config),
    )


def _require_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PackError(f"{field_name} must be an object")
    return value


def _require_list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise PackError(f"{field_name} must be an array")
    return value


def _require_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PackError(f"{field_name} must be a non-empty string")
    return value


def _require_int(value: Any, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise PackError(f"{field_name} must be an integer")
    return value


def parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise PackError(f"{field_name} must be an ISO date") from exc


def pack_from_dict(data: dict[str, Any]) -> Pack:
    schema = _require_int(data.get("schema"), "schema")
    if schema != 1:
        raise PackError(f"unsupported pack schema: {schema}")

    source_data = _require_mapping(data.get("source"), "source")
    source = Source(
        name=_require_str(source_data.get("name"), "source.name"),
        url=_require_str(source_data.get("url"), "source.url"),
        revision=_require_str(source_data.get("revision"), "source.revision"),
        license=_require_str(source_data.get("license"), "source.license"),
    )
    exam_data = _require_mapping(data.get("exam"), "exam")
    exam = ExamRules(
        questions=_require_int(exam_data.get("questions"), "exam.questions"),
        passing=_require_int(exam_data.get("passing"), "exam.passing"),
    )

    groups: list[Group] = []
    for raw_group in _require_list(data.get("groups"), "groups"):
        group_data = _require_mapping(raw_group, "group")
        groups.append(
            Group(
                id=_require_str(group_data.get("id"), "group.id"),
                name=_require_str(group_data.get("name"), "group.name"),
                subelement=_require_str(group_data.get("subelement"), "group.subelement"),
                exam_questions=_require_int(
                    group_data.get("exam_questions"), "group.exam_questions"
                ),
            )
        )
    if not groups:
        raise PackError("pack must contain at least one group")
    group_ids = [group.id for group in groups]
    if len(group_ids) != len(set(group_ids)):
        raise PackError("group IDs must be unique")
    if any(group.exam_questions < 1 for group in groups):
        raise PackError("each group must provide at least one exam question")

    questions: list[Question] = []
    for raw_question in _require_list(data.get("questions"), "questions"):
        question_data = _require_mapping(raw_question, "question")
        question_id = _require_str(question_data.get("id"), "question.id")
        group_id = _require_str(question_data.get("group"), "question.group")
        if group_id not in set(group_ids):
            raise PackError(f"{question_id}: unknown group {group_id}")

        raw_choices = _require_list(question_data.get("choices"), f"{question_id}.choices")
        if len(raw_choices) != 4:
            raise PackError(f"{question_id}: expected four choices")
        choices: list[Choice] = []
        for raw_choice in raw_choices:
            choice_data = _require_mapping(raw_choice, f"{question_id}.choice")
            choice_id = _require_str(choice_data.get("id"), f"{question_id}.choice.id")
            if choice_id not in {"A", "B", "C", "D"}:
                raise PackError(f"{question_id}: invalid choice ID {choice_id}")
            choices.append(
                Choice(
                    id=choice_id,
                    text=_require_str(choice_data.get("text"), f"{question_id}.choice.text"),
                )
            )
        choice_ids = [choice.id for choice in choices]
        if sorted(choice_ids) != ["A", "B", "C", "D"]:
            raise PackError(f"{question_id}: choices must be A, B, C, and D")
        correct = _require_str(question_data.get("correct"), f"{question_id}.correct")
        if correct not in set(choice_ids):
            raise PackError(f"{question_id}: correct answer is not one of the choices")

        reference = question_data.get("reference")
        if reference is not None and not isinstance(reference, str):
            raise PackError(f"{question_id}: reference must be a string or null")
        figure = question_data.get("figure")
        if figure is not None and not isinstance(figure, str):
            raise PackError(f"{question_id}: figure must be a string or null")

        questions.append(
            Question(
                id=question_id,
                group=group_id,
                text=_require_str(question_data.get("text"), f"{question_id}.text"),
                choices=tuple(sorted(choices, key=lambda choice: choice.id)),
                correct=correct,
                reference=reference or None,
                figure=figure or None,
            )
        )

    question_ids = [question.id for question in questions]
    if len(question_ids) != len(set(question_ids)):
        raise PackError("question IDs must be unique")

    questions_by_group: dict[str, list[Question]] = {group.id: [] for group in groups}
    for question in questions:
        questions_by_group[question.group].append(question)
    for group in groups:
        if len(questions_by_group[group.id]) < group.exam_questions:
            raise PackError(f"group {group.id} does not have enough questions")

    actual_exam_questions = sum(group.exam_questions for group in groups)
    if actual_exam_questions != exam.questions:
        raise PackError(
            f"exam.questions is {exam.questions}, but groups provide "
            f"{actual_exam_questions}"
        )
    if not 0 < exam.passing <= exam.questions:
        raise PackError("exam.passing must be within the exam question count")

    return Pack(
        schema=schema,
        id=_require_str(data.get("id"), "id"),
        country=_require_str(data.get("country"), "country"),
        country_name=_require_str(data.get("country_name"), "country_name"),
        license_class=_require_str(data.get("license_class"), "license_class"),
        license_name=_require_str(data.get("license_name"), "license_name"),
        element=_require_int(data.get("element"), "element"),
        effective=parse_date(
            _require_str(data.get("effective"), "effective"), "effective"
        ),
        expires=parse_date(_require_str(data.get("expires"), "expires"), "expires"),
        source=source,
        exam=exam,
        groups=tuple(groups),
        questions=tuple(questions),
    )


def pack_summary_from_dict(data: dict[str, Any]) -> PackSummary:
    source_data = _require_mapping(data.get("source"), "source")
    exam_data = _require_mapping(data.get("exam"), "exam")
    return PackSummary(
        id=_require_str(data.get("id"), "id"),
        country=_require_str(data.get("country"), "country"),
        country_name=_require_str(data.get("country_name"), "country_name"),
        license_class=_require_str(data.get("license_class"), "license_class"),
        license_name=_require_str(data.get("license_name"), "license_name"),
        element=_require_int(data.get("element"), "element"),
        effective=parse_date(
            _require_str(data.get("effective"), "effective"), "effective"
        ),
        expires=parse_date(_require_str(data.get("expires"), "expires"), "expires"),
        source=Source(
            name=_require_str(source_data.get("name"), "source.name"),
            url=_require_str(source_data.get("url"), "source.url"),
            revision=_require_str(source_data.get("revision"), "source.revision"),
            license=_require_str(source_data.get("license"), "source.license"),
        ),
        exam=ExamRules(
            questions=_require_int(exam_data.get("questions"), "exam.questions"),
            passing=_require_int(exam_data.get("passing"), "exam.passing"),
        ),
        question_count=_require_int(data.get("question_count"), "question_count"),
        group_count=_require_int(data.get("group_count"), "group_count"),
    )


def pack_summary(pack: Pack) -> PackSummary:
    return PackSummary(
        id=pack.id,
        country=pack.country,
        country_name=pack.country_name,
        license_class=pack.license_class,
        license_name=pack.license_name,
        element=pack.element,
        effective=pack.effective,
        expires=pack.expires,
        source=pack.source,
        exam=pack.exam,
        question_count=len(pack.questions),
        group_count=len(pack.groups),
    )


def pack_to_dict(pack: Pack) -> dict[str, Any]:
    """Serialize a pack deterministically, mainly for validation fixtures."""
    return {
        "schema": pack.schema,
        "id": pack.id,
        "country": pack.country,
        "country_name": pack.country_name,
        "license_class": pack.license_class,
        "license_name": pack.license_name,
        "element": pack.element,
        "effective": pack.effective.isoformat(),
        "expires": pack.expires.isoformat(),
        "source": {
            "name": pack.source.name,
            "url": pack.source.url,
            "revision": pack.source.revision,
            "license": pack.source.license,
        },
        "exam": {"questions": pack.exam.questions, "passing": pack.exam.passing},
        "groups": [
            {
                "id": group.id,
                "name": group.name,
                "subelement": group.subelement,
                "exam_questions": group.exam_questions,
            }
            for group in pack.groups
        ],
        "questions": [
            {
                "id": question.id,
                "group": question.group,
                "text": question.text,
                "choices": [
                    {"id": choice.id, "text": choice.text}
                    for choice in question.choices
                ],
                "correct": question.correct,
                "reference": question.reference,
                "figure": question.figure,
            }
            for question in pack.questions
        ],
    }
