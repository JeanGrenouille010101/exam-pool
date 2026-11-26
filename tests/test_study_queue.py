from __future__ import annotations

from random import Random

from exam_pool.domain.models import MasteryConfig, Progress, apply_answer
from exam_pool.domain.study_queue import StudyQueue

CONFIG = MasteryConfig(min_attempts=3, target_accuracy=0.8, missed_gap=5)


def wrong(progress: Progress) -> Progress:
    return apply_answer(
        progress,
        correct=False,
        content_hash="h",
        config=CONFIG,
    ).progress


def test_correct_answer_does_not_repeat_in_same_session(pack) -> None:
    queue = StudyQueue.for_pack(pack, {}, CONFIG, Random(1))
    question = queue.next_question()
    assert question is not None
    queue.submit(True, Progress(pack.id, question.id, content_hash="h"))
    assert queue.remaining == len(pack.questions) - 1
    assert queue.current is None


def test_first_miss_returns_later_in_session(pack) -> None:
    queue = StudyQueue.for_pack(pack, {}, CONFIG, Random(2))
    question = queue.next_question()
    assert question is not None
    progress = wrong(Progress(pack.id, question.id, content_hash="h"))
    queue.submit(False, progress)

    seen = []
    for _ in range(5):
        next_question = queue.next_question()
        assert next_question is not None
        seen.append(next_question.id)
        queue.submit(True, Progress(pack.id, next_question.id, content_hash="h"))

    assert question.id not in seen
    assert queue.next_question().id == question.id


def test_consecutive_misses_move_question_to_front(pack) -> None:
    queue = StudyQueue.for_pack(pack, {}, CONFIG, Random(3))
    question = queue.next_question()
    assert question is not None
    progress = Progress(pack.id, question.id, content_hash="h")
    progress = wrong(progress)
    progress = wrong(progress)
    queue.submit(False, progress)
    assert queue.next_question().id == question.id


def test_mastered_questions_are_not_queued(pack) -> None:
    mastered = Progress(
        pack.id,
        pack.questions[0].id,
        times_asked=5,
        times_correct=5,
        last_result="correct",
        content_hash="h",
    )
    queue = StudyQueue.for_pack(pack, {mastered.question_id: mastered}, CONFIG, Random(4))
    assert queue.remaining == len(pack.questions) - 1
    queued = []
    while (question := queue.next_question()) is not None:
        queued.append(question.id)
        queue.submit(True, Progress(pack.id, question.id, content_hash="h"))
    assert mastered.question_id not in queued


def test_queue_restores_saved_order_and_answered_count(pack) -> None:
    ids = [question.id for question in pack.questions]
    queue = StudyQueue.for_pack(
        pack, {}, CONFIG, queue_ids=ids, answered=4
    )
    assert queue.answered == 4
    assert queue.queue_ids == tuple(ids)

    current = queue.next_question()
    assert current is not None
    assert current.id == ids[0]
    assert queue.queue_ids == tuple(ids[1:])


def test_queue_restores_current_question(pack) -> None:
    ids = [question.id for question in pack.questions]
    queue = StudyQueue.for_pack(
        pack, {}, CONFIG, queue_ids=ids[1:], answered=1
    )
    question = queue.restore_current(ids[0])
    assert question is not None
    assert question.id == ids[0]
    assert queue.current is not None
    assert queue.current.id == ids[0]
    assert queue.queue_ids == tuple(ids[1:])


def test_queue_restore_drops_unknown_questions(pack) -> None:
    queue = StudyQueue.for_pack(
        pack,
        {},
        CONFIG,
        queue_ids=["missing", pack.questions[0].id],
    )
    assert queue.queue_ids == (pack.questions[0].id,)
    assert queue.restore_current("missing") is None
