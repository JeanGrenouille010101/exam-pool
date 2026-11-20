from __future__ import annotations

from copy import deepcopy

import pytest

from exam_pool.domain.models import pack_from_dict


def make_pack_dict() -> dict:
    groups = []
    questions = []
    for group_index in range(4):
        group_id = f"T{group_index}A"
        groups.append(
            {
                "id": group_id,
                "name": f"Group {group_id}",
                "subelement": f"T{group_index}",
                "exam_questions": 1,
            }
        )
        for question_index in range(2):
            qid = f"{group_id}{question_index + 1:02d}"
            questions.append(
                {
                    "id": qid,
                    "group": group_id,
                    "text": f"Question {qid}?",
                    "choices": [
                        {"id": "A", "text": f"{qid} answer A"},
                        {"id": "B", "text": f"{qid} answer B"},
                        {"id": "C", "text": f"{qid} answer C"},
                        {"id": "D", "text": f"{qid} answer D"},
                    ],
                    "correct": "C",
                    "reference": "97.1",
                    "figure": None,
                }
            )
    return {
        "schema": 1,
        "id": "us-test-2026",
        "country": "US",
        "country_name": "United States",
        "license_class": "test",
        "license_name": "Test Class",
        "element": 2,
        "effective": "2026-01-01",
        "expires": "2030-01-01",
        "source": {
            "name": "NCVEC",
            "url": "https://example.invalid/pool.pdf",
            "revision": "test",
            "license": "Public domain",
        },
        "exam": {"questions": 4, "passing": 3},
        "groups": groups,
        "questions": questions,
    }


@pytest.fixture
def pack_dict() -> dict:
    return make_pack_dict()


@pytest.fixture
def pack(pack_dict: dict):
    return pack_from_dict(deepcopy(pack_dict))
