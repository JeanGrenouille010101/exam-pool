from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from ..domain.exam import ExamQuestion, build_exam, score_exam
from ..domain.models import (
    AnswerOutcome,
    MasteryConfig,
    Pack,
    Progress,
    Question,
    apply_answer,
    is_mastered,
)


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path) if path != ":memory:" else Path(":memory:")
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if str(path) != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._migrate()

    def close(self) -> None:
        self._conn.close()

    def _migrate(self) -> None:
        with self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)"
            )
            row = self._conn.execute("SELECT version FROM schema_version").fetchone()
            version = int(row["version"]) if row else 0
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"database schema {version} is newer than supported "
                    f"version {SCHEMA_VERSION}"
                )
            if version < 1:
                self._conn.executescript(
                    """
                    CREATE TABLE question_progress (
                        pack_id TEXT NOT NULL,
                        question_id TEXT NOT NULL,
                        times_asked INTEGER NOT NULL DEFAULT 0,
                        times_correct INTEGER NOT NULL DEFAULT 0,
                        consecutive_correct INTEGER NOT NULL DEFAULT 0,
                        consecutive_wrong INTEGER NOT NULL DEFAULT 0,
                        last_result TEXT,
                        content_hash TEXT NOT NULL DEFAULT '',
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (pack_id, question_id)
                    );

                    CREATE TABLE attempts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pack_id TEXT NOT NULL,
                        question_id TEXT NOT NULL,
                        mode TEXT NOT NULL CHECK (mode IN ('study', 'test')),
                        session_id TEXT,
                        selected TEXT,
                        correct INTEGER NOT NULL,
                        answered_at TEXT NOT NULL,
                        response_ms INTEGER
                    );
                    CREATE INDEX attempts_pack_question
                        ON attempts (pack_id, question_id);
                    CREATE INDEX attempts_pack_time
                        ON attempts (pack_id, answered_at);

                    CREATE TABLE test_sessions (
                        id TEXT PRIMARY KEY,
                        pack_id TEXT NOT NULL,
                        mode TEXT NOT NULL CHECK (mode IN ('timed', 'untimed')),
                        started_at TEXT NOT NULL,
                        finished_at TEXT,
                        time_limit_seconds INTEGER,
                        elapsed_seconds INTEGER,
                        total_questions INTEGER NOT NULL,
                        correct_count INTEGER,
                        passing INTEGER NOT NULL,
                        passed INTEGER,
                        status TEXT NOT NULL DEFAULT 'in_progress'
                            CHECK (status IN ('in_progress', 'completed', 'abandoned')),
                        questions_json TEXT NOT NULL,
                        answers_json TEXT NOT NULL DEFAULT '{}'
                    );
                    CREATE INDEX test_sessions_pack_time
                        ON test_sessions (pack_id, started_at);

                    CREATE TABLE test_answers (
                        session_id TEXT NOT NULL
                            REFERENCES test_sessions (id) ON DELETE CASCADE,
                        position INTEGER NOT NULL,
                        question_id TEXT NOT NULL,
                        selected TEXT,
                        correct INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (session_id, position)
                    );
                    """
                )
                self._conn.execute(
                    "INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,)
                )
            elif version < SCHEMA_VERSION:
                raise RuntimeError(f"no migration from schema {version}")

    # ------------------------------------------------------------------
    # Study progress

    def get_progress(self, pack_id: str) -> dict[str, Progress]:
        rows = self._conn.execute(
            "SELECT * FROM question_progress WHERE pack_id = ?", (pack_id,)
        ).fetchall()
        return {row["question_id"]: self._progress_from_row(row) for row in rows}

    def get_progress_for(self, pack_id: str, question_id: str) -> Progress:
        row = self._conn.execute(
            "SELECT * FROM question_progress WHERE pack_id = ? AND question_id = ?",
            (pack_id, question_id),
        ).fetchone()
        if row is None:
            return Progress(pack_id, question_id)
        return self._progress_from_row(row)

    def record_study_answer(
        self,
        pack: Pack,
        question: Question,
        selected: str,
        config: MasteryConfig,
        *,
        session_id: str | None = None,
        response_ms: int | None = None,
    ) -> AnswerOutcome:
        correct = selected == question.correct
        progress = self.get_progress_for(pack.id, question.id)
        outcome = apply_answer(
            progress,
            correct=correct,
            content_hash=question.content_hash,
            config=config,
        )
        now = utc_now()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO question_progress (
                    pack_id, question_id, times_asked, times_correct,
                    consecutive_correct, consecutive_wrong, last_result,
                    content_hash, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (pack_id, question_id) DO UPDATE SET
                    times_asked = excluded.times_asked,
                    times_correct = excluded.times_correct,
                    consecutive_correct = excluded.consecutive_correct,
                    consecutive_wrong = excluded.consecutive_wrong,
                    last_result = excluded.last_result,
                    content_hash = excluded.content_hash,
                    updated_at = excluded.updated_at
                """,
                (
                    outcome.progress.pack_id,
                    outcome.progress.question_id,
                    outcome.progress.times_asked,
                    outcome.progress.times_correct,
                    outcome.progress.consecutive_correct,
                    outcome.progress.consecutive_wrong,
                    outcome.progress.last_result,
                    outcome.progress.content_hash,
                    now,
                ),
            )
            self._conn.execute(
                """
                INSERT INTO attempts (
                    pack_id, question_id, mode, session_id, selected,
                    correct, answered_at, response_ms
                ) VALUES (?, ?, 'study', ?, ?, ?, ?, ?)
                """,
                (
                    pack.id,
                    question.id,
                    session_id,
                    selected,
                    int(correct),
                    now,
                    response_ms,
                ),
            )
        return outcome

    def _progress_from_row(self, row: sqlite3.Row) -> Progress:
        return Progress(
            pack_id=row["pack_id"],
            question_id=row["question_id"],
            times_asked=row["times_asked"],
            times_correct=row["times_correct"],
            consecutive_correct=row["consecutive_correct"],
            consecutive_wrong=row["consecutive_wrong"],
            last_result=row["last_result"],
            content_hash=row["content_hash"],
        )

    def count_attempts(self, pack_id: str, mode: str | None = None) -> int:
        if mode:
            row = self._conn.execute(
                "SELECT COUNT(*) AS count FROM attempts WHERE pack_id = ? AND mode = ?",
                (pack_id, mode),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT COUNT(*) AS count FROM attempts WHERE pack_id = ?",
                (pack_id,),
            ).fetchone()
        return int(row["count"])

    def reset_progress(self, pack_id: str | None = None) -> None:
        with self._conn:
            if pack_id:
                self._conn.execute(
                    "DELETE FROM question_progress WHERE pack_id = ?", (pack_id,)
                )
                self._conn.execute("DELETE FROM attempts WHERE pack_id = ?", (pack_id,))
                self._conn.execute(
                    "DELETE FROM test_sessions WHERE pack_id = ?", (pack_id,)
                )
            else:
                self._conn.execute("DELETE FROM question_progress")
                self._conn.execute("DELETE FROM attempts")
                self._conn.execute("DELETE FROM test_sessions")

    # ------------------------------------------------------------------
    # Tests

    def start_test_session(
        self,
        pack: Pack,
        *,
        mode: str,
        time_limit_seconds: int | None,
        exam: tuple[ExamQuestion, ...] | None = None,
    ) -> str:
        if mode not in {"timed", "untimed"}:
            raise ValueError(f"unknown test mode: {mode}")
        if mode == "timed" and (time_limit_seconds is None or time_limit_seconds <= 0):
            raise ValueError("timed tests require a positive time limit")
        if mode == "untimed":
            time_limit_seconds = None

        exam = exam or build_exam(pack)
        session_id = str(uuid.uuid4())
        questions_payload = [
            {
                "question_id": item.question.id,
                "choice_order": list(item.choice_order),
            }
            for item in exam
        ]
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO test_sessions (
                    id, pack_id, mode, started_at, time_limit_seconds,
                    total_questions, passing, status, questions_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'in_progress', ?)
                """,
                (
                    session_id,
                    pack.id,
                    mode,
                    utc_now(),
                    time_limit_seconds,
                    len(exam),
                    pack.exam.passing,
                    json.dumps(questions_payload, separators=(",", ":")),
                ),
            )
        return session_id

    def get_test_session(self, session_id: str) -> sqlite3.Row:
        row = self._conn.execute(
            "SELECT * FROM test_sessions WHERE id = ?", (session_id,)
        ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return row

    def get_test_questions(self, session_id: str) -> list[dict]:
        row = self.get_test_session(session_id)
        return json.loads(row["questions_json"])

    def get_test_answers(self, session_id: str) -> dict[int, str]:
        rows = self._conn.execute(
            "SELECT position, selected FROM test_answers WHERE session_id = ?",
            (session_id,),
        ).fetchall()
        return {
            int(row["position"]): row["selected"]
            for row in rows
            if row["selected"] is not None
        }

    def save_test_answer(
        self,
        session_id: str,
        position: int,
        question: Question,
        selected: str | None,
    ) -> None:
        correct = selected == question.correct if selected else False
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO test_answers (
                    session_id, position, question_id, selected, correct
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (session_id, position) DO UPDATE SET
                    question_id = excluded.question_id,
                    selected = excluded.selected,
                    correct = excluded.correct
                """,
                (session_id, position, question.id, selected, int(correct)),
            )

    def finish_test_session(
        self,
        session_id: str,
        *,
        elapsed_seconds: int | None = None,
    ) -> dict[str, int | bool]:
        session = self.get_test_session(session_id)
        if session["status"] != "in_progress":
            raise RuntimeError(f"test session is {session['status']}")
        rows = self._conn.execute(
            "SELECT correct FROM test_answers WHERE session_id = ?", (session_id,)
        ).fetchall()
        correct = sum(int(row["correct"]) for row in rows)
        total = int(session["total_questions"])
        passing = int(session["passing"])
        passed = correct >= passing
        finished = utc_now()
        with self._conn:
            self._conn.execute(
                """
                UPDATE test_sessions SET
                    status = 'completed', finished_at = ?, correct_count = ?,
                    passed = ?, elapsed_seconds = ?
                WHERE id = ?
                """,
                (finished, correct, int(passed), elapsed_seconds, session_id),
            )
        return {
            "correct": correct,
            "total": total,
            "passing": passing,
            "passed": passed,
        }

    def abandon_test_session(self, session_id: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE test_sessions SET status = 'abandoned', finished_at = ? "
                "WHERE id = ? AND status = 'in_progress'",
                (utc_now(), session_id),
            )

    # ------------------------------------------------------------------
    # Statistics

    def get_stats(self, pack: Pack, config: MasteryConfig) -> dict:
        progress = self.get_progress(pack.id)
        total = len(pack.questions)
        attempted = sum(1 for question in pack.questions if question.id in progress)
        mastered = sum(
            1
            for question in pack.questions
            if question.id in progress and is_mastered(progress[question.id], config)
        )
        unseen = total - attempted
        study_correct = sum(item.times_correct for item in progress.values())
        study_asked = sum(item.times_asked for item in progress.values())

        test_row = self._conn.execute(
            """
            SELECT COUNT(*) AS tests, AVG(correct_count * 100.0 / total_questions)
                AS average_score
            FROM test_sessions
            WHERE pack_id = ? AND status = 'completed'
            """,
            (pack.id,),
        ).fetchone()
        return {
            "total": total,
            "attempted": attempted,
            "mastered": mastered,
            "unseen": unseen,
            "study_asked": study_asked,
            "study_correct": study_correct,
            "study_accuracy": (100.0 * study_correct / study_asked)
            if study_asked
            else 0.0,
            "tests": int(test_row["tests"] or 0),
            "average_score": float(test_row["average_score"] or 0.0),
        }

    def most_missed(
        self, pack: Pack, limit: int = 5, min_attempts: int = 3
    ) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT question_id, times_asked, times_correct,
                   (times_asked - times_correct) AS missed,
                   (times_asked - times_correct) * 1.0 / times_asked AS miss_rate
            FROM question_progress
            WHERE pack_id = ? AND times_asked >= ?
            ORDER BY missed DESC, miss_rate DESC, question_id
            LIMIT ?
            """,
            (pack.id, min_attempts, limit),
        ).fetchall()
        return [self._with_question(pack, dict(row)) for row in rows]

    def most_correct(
        self, pack: Pack, limit: int = 5, min_attempts: int = 3
    ) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT question_id, times_asked, times_correct,
                   (times_asked - times_correct) AS missed,
                   times_correct * 1.0 / times_asked AS accuracy
            FROM question_progress
            WHERE pack_id = ? AND times_asked >= ?
            ORDER BY times_correct DESC, accuracy DESC, question_id
            LIMIT ?
            """,
            (pack.id, min_attempts, limit),
        ).fetchall()
        return [self._with_question(pack, dict(row)) for row in rows]

    def _with_question(self, pack: Pack, row: dict) -> dict:
        question = pack.question_map.get(row["question_id"])
        if question is not None:
            row["text"] = question.text
            row["reference"] = question.reference
        else:
            row["text"] = row["question_id"]
            row["reference"] = None
        return row

    def score_history(self, pack_id: str, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT finished_at, correct_count, total_questions, mode
            FROM test_sessions
            WHERE pack_id = ? AND status = 'completed'
            ORDER BY finished_at DESC
            LIMIT ?
            """,
            (pack_id, limit),
        ).fetchall()
        history = [
            {
                "finished_at": row["finished_at"],
                "score": 100.0 * int(row["correct_count"]) / int(row["total_questions"]),
                "correct": int(row["correct_count"]),
                "total": int(row["total_questions"]),
                "mode": row["mode"],
            }
            for row in rows
        ]
        return list(reversed(history))
