from __future__ import annotations

import re

from exam_pool.data.packs import PackRepository
from exam_pool.domain.models import MasteryConfig, PackError

EXPECTED = {
    "technician": {
        "id": "us-technician-2026",
        "questions": 409,
        "groups": 35,
        "exam": 35,
        "passing": 26,
        "figures": 12,
        "effective": "2026-07-01",
    },
    "general": {
        "id": "us-general-2023",
        "questions": 423,
        "groups": 35,
        "exam": 35,
        "passing": 26,
        "figures": 5,
        "effective": "2023-07-01",
    },
    "extra": {
        "id": "us-extra-2024",
        "questions": 599,
        "groups": 50,
        "exam": 50,
        "passing": 37,
        "figures": 27,
        "effective": "2024-07-01",
    },
}


def test_bundled_packs_are_complete() -> None:
    packs = PackRepository().load_all()
    assert {pack.license_class for pack in packs} == set(EXPECTED)

    for pack in packs:
        expected = EXPECTED[pack.license_class]
        assert pack.id == expected["id"]
        assert len(pack.questions) == expected["questions"]
        assert len(pack.groups) == expected["groups"]
        assert pack.exam.questions == expected["exam"]
        assert pack.exam.passing == expected["passing"]
        assert pack.effective.isoformat() == expected["effective"]
        assert sum(group.exam_questions for group in pack.groups) == expected["exam"]
        assert len({question.id for question in pack.questions}) == len(pack.questions)
        assert len({group.id for group in pack.groups}) == len(pack.groups)
        assert all(group.name.strip() for group in pack.groups)
        assert sum(1 for question in pack.questions if question.figure) == expected["figures"]

        for question in pack.questions:
            assert len(question.choices) == 4
            assert {choice.id for choice in question.choices} == {"A", "B", "C", "D"}
            assert question.correct in {choice.id for choice in question.choices}
            assert question.text.strip()
            assert not re.search(r"\b(?:Errata|FCC Element)\b", question.text)
            for choice in question.choices:
                assert choice.text.strip()


def test_all_bundled_figures_resolve() -> None:
    repository = PackRepository()
    missing = []
    for pack in repository.load_all():
        for question in pack.questions:
            if question.figure and repository.figure_path(question.figure) is None:
                missing.append(f"{pack.id}:{question.id}:{question.figure}")
    assert not missing


def test_pack_validation_rejects_wrong_exam_size(pack_dict) -> None:
    pack_dict["exam"]["questions"] = 35
    try:
        from exam_pool.domain.models import pack_from_dict

        pack_from_dict(pack_dict)
    except PackError as exc:
        assert "exam.questions" in str(exc)
    else:
        raise AssertionError("expected invalid exam size to be rejected")


def test_mastery_config_defaults() -> None:
    config = MasteryConfig()
    assert config.min_attempts == 3
    assert config.target_accuracy == 0.8
    assert config.missed_gap == 5
