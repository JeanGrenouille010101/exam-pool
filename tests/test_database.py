from __future__ import annotations

from random import Random

import pytest

from exam_pool.data.database import Database
from exam_pool.domain.exam import ExamQuestion, build_exam
from exam_pool.domain.models import MasteryConfig, is_mastered

CONFIG = MasteryConfig(min_attempts=3, target_accuracy=0.8, missed_gap=5)


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "progress.db")
    yield database
    database.close()


def correct_answer(question):
    return question.correct


def wrong_answer(question):
    return next(choice for choice in "ABCD" if choice != question.correct)


def test_study_answers_persist_and_master(db, pack) -> None:
    question = pack.questions[0]
    for _ in range(3):
        db.record_study_answer(
            pack,
            question,
            correct_answer(question),
            CONFIG,
        )
    progress = db.get_progress_for(pack.id, question.id)
    assert progress.times_asked == 3
    assert progress.times_correct == 3
    assert is_mastered(progress, CONFIG)
    assert db.count_attempts(pack.id, "study") == 3

    db.close()
    db = Database(db.path)
    assert db.get_progress_for(pack.id, question.id).times_asked == 3


def test_wrong_answers_are_recorded_and_mastery_revoked(db, pack) -> None:
    question = pack.questions[0]
    for _ in range(3):
        db.record_study_answer(pack, question, correct_answer(question), CONFIG)
    assert is_mastered(db.get_progress_for(pack.id, question.id), CONFIG)

    db.record_study_answer(pack, question, wrong_answer(question), CONFIG)
    progress = db.get_progress_for(pack.id, question.id)
    assert progress.times_asked == 4
    assert progress.times_correct == 3
    assert progress.consecutive_wrong == 1
    assert not is_mastered(progress, CONFIG)


def test_changed_content_hash_resets_progress(db, pack) -> None:
    question = pack.questions[0]
    for _ in range(3):
        db.record_study_answer(pack, question, correct_answer(question), CONFIG)

    changed = type(question)(
        id=question.id,
        group=question.group,
        text=question.text + " changed",
        choices=question.choices,
        correct=question.correct,
        reference=question.reference,
        figure=question.figure,
    )
    db.record_study_answer(pack, changed, correct_answer(changed), CONFIG)
    progress = db.get_progress_for(pack.id, question.id)
    assert progress.times_asked == 1
    assert progress.times_correct == 1


def test_test_session_scoring_history_and_stats(db, pack) -> None:
    exam = build_exam(pack, Random(11))
    session_id = db.start_test_session(
        pack, mode="timed", time_limit_seconds=1800, exam=exam
    )
    for position, item in enumerate(exam):
        selected = (
            item.question.correct
            if position < 3
            else wrong_answer(item.question)
        )
        db.save_test_answer(session_id, position, item.question, selected)

    result = db.finish_test_session(session_id, elapsed_seconds=123)
    assert result == {"correct": 3, "total": 4, "passing": 3, "passed": True}

    session = db.get_test_session(session_id)
    assert session["status"] == "completed"
    assert session["elapsed_seconds"] == 123
    assert db.get_test_answers(session_id) == {
        position: item.question.correct if position < 3 else wrong_answer(item.question)
        for position, item in enumerate(exam)
    }

    stats = db.get_stats(pack, CONFIG)
    assert stats["tests"] == 1
    assert stats["average_score"] == 75.0

    history = db.score_history(pack.id)
    assert len(history) == 1
    assert history[0]["score"] == 75.0
    assert history[0]["mode"] == "timed"


def test_unanswered_test_questions_count_as_wrong(db, pack) -> None:
    exam = build_exam(pack, Random(12))
    session_id = db.start_test_session(
        pack, mode="untimed", time_limit_seconds=None, exam=exam
    )
    db.save_test_answer(session_id, 0, exam[0].question, exam[0].question.correct)
    result = db.finish_test_session(session_id)
    assert result["correct"] == 1
    assert result["passed"] is False


def test_timed_session_requires_positive_limit(db, pack) -> None:
    with pytest.raises(ValueError):
        db.start_test_session(pack, mode="timed", time_limit_seconds=None)
    with pytest.raises(ValueError):
        db.start_test_session(pack, mode="timed", time_limit_seconds=0)


def test_most_missed_and_most_correct_require_minimum_attempts(db, pack) -> None:
    q1, q2 = pack.questions[:2]
    for _ in range(3):
        db.record_study_answer(pack, q1, wrong_answer(q1), CONFIG)
    for _ in range(4):
        db.record_study_answer(pack, q2, correct_answer(q2), CONFIG)

    missed = db.most_missed(pack)
    assert missed[0]["question_id"] == q1.id
    assert missed[0]["missed"] == 3

    correct = db.most_correct(pack)
    assert correct[0]["question_id"] == q2.id
    assert correct[0]["times_correct"] == 4


def test_test_answers_are_included_in_coverage_and_most_missed(db, pack) -> None:
    question = pack.questions[0]
    exam = (ExamQuestion(question, question.choice_ids),)
    for _ in range(3):
        session_id = db.start_test_session(
            pack, mode="untimed", time_limit_seconds=None, exam=exam
        )
        db.save_test_answer(session_id, 0, question, wrong_answer(question))
        db.finish_test_session(session_id)

    stats = db.get_stats(pack, CONFIG)
    assert stats["attempted"] == 1
    assert stats["unseen"] == len(pack.questions) - 1
    missed = db.most_missed(pack)
    assert missed[0]["question_id"] == question.id
    assert missed[0]["times_asked"] == 3


def test_reset_progress_removes_attempts_and_tests(db, pack) -> None:
    exam = build_exam(pack, Random(13))
    session_id = db.start_test_session(
        pack, mode="untimed", time_limit_seconds=None, exam=exam
    )
    db.save_test_answer(session_id, 0, exam[0].question, exam[0].question.correct)
    db.finish_test_session(session_id)
    db.record_study_answer(pack, pack.questions[0], pack.questions[0].correct, CONFIG)

    db.reset_progress(pack.id)
    assert db.get_progress(pack.id) == {}
    assert db.count_attempts(pack.id) == 0
    assert db.score_history(pack.id) == []
