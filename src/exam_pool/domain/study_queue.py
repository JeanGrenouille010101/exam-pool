from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from random import Random

from .models import MasteryConfig, Pack, Progress, Question, is_mastered


class StudyQueue:
    """Ordering for one study session.

    A session initially contains every question that is not mastered. Questions
    answered correctly leave the session; mastery is accumulated across
    sessions. Wrong answers return later in the session, and a question that
    has been missed consecutively moves to the front.
    """

    def __init__(
        self,
        questions: Iterable[Question],
        progress: Mapping[str, Progress],
        config: MasteryConfig,
        rng: Random | None = None,
        *,
        queue_ids: Iterable[str] | None = None,
        answered: int = 0,
    ) -> None:
        questions = tuple(questions)
        self._questions = {question.id: question for question in questions}
        self._config = config
        self._rng = rng or Random()
        self._current: Question | None = None
        self._answered = max(0, int(answered))
        self._queue: deque[str] = deque()
        if queue_ids is not None:
            self._queue.extend(
                question_id
                for question_id in queue_ids
                if question_id in self._questions
            )
            return
        available = [
            question.id
            for question in questions
            if not is_mastered(
                progress.get(question.id, Progress("", question.id)), config
            )
        ]
        self._rng.shuffle(available)
        self._queue.extend(available)

    @classmethod
    def for_pack(
        cls,
        pack: Pack,
        progress: Mapping[str, Progress],
        config: MasteryConfig,
        rng: Random | None = None,
        *,
        queue_ids: Iterable[str] | None = None,
        answered: int = 0,
    ) -> StudyQueue:
        return cls(
            pack.questions,
            progress,
            config,
            rng,
            queue_ids=queue_ids,
            answered=answered,
        )

    @property
    def current(self) -> Question | None:
        return self._current

    @property
    def answered(self) -> int:
        return self._answered

    @property
    def remaining(self) -> int:
        return len(self._queue)

    @property
    def queue_ids(self) -> tuple[str, ...]:
        return tuple(self._queue)

    @property
    def total_estimate(self) -> int:
        return self._answered + len(self._queue)

    @property
    def finished(self) -> bool:
        return self._current is None and not self._queue

    def next_question(self) -> Question | None:
        if self._current is not None:
            raise RuntimeError("answer the current question before advancing")
        if not self._queue:
            return None
        self._current = self._questions[self._queue.popleft()]
        return self._current

    def restore_current(self, question_id: str | None) -> Question | None:
        """Restore an already-presented question without advancing the queue."""
        if self._current is not None:
            raise RuntimeError("a question is already current")
        if question_id is None:
            return None
        question = self._questions.get(question_id)
        if question is None:
            return None
        self._current = question
        return question

    def submit(self, correct: bool, progress: Progress) -> None:
        """Advance the queue after an answer has been applied to progress."""
        if self._current is None:
            raise RuntimeError("no current question")
        question_id = self._current.id
        self._current = None
        self._answered += 1

        if correct:
            return

        if progress.consecutive_wrong >= 2:
            self._queue.appendleft(question_id)
        else:
            position = min(self._config.missed_gap, len(self._queue))
            self._queue.insert(position, question_id)
