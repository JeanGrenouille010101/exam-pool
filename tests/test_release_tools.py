from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_tool(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bump_version = load_tool("bump_version")
validate_packs = load_tool("validate_packs")


def test_next_version_bumps_each_part() -> None:
    assert bump_version.next_version("0.3.6", "patch") == "0.3.7"
    assert bump_version.next_version("0.3.6", "minor") == "0.4.0"
    assert bump_version.next_version("0.3.6", "major") == "1.0.0"


def test_add_release_entry_escapes_and_rejects_duplicates() -> None:
    text = (
        "<component>\n"
        "  <releases>\n"
        "    <release version=\"0.3.6\" date=\"2026-11-26\">\n"
        "      <description><p>Old</p></description>\n"
        "    </release>\n"
        "  </releases>\n"
        "</component>\n"
    )
    result = bump_version.add_release_entry(
        text, "0.3.7", "2026-11-27", "Update pools <and> figures & more"
    )
    assert '<release version="0.3.7" date="2026-11-27">' in result
    assert "&lt;and&gt;" in result
    assert "&amp; more" in result
    assert result.index('version="0.3.7"') < result.index('version="0.3.6"')

    with pytest.raises(RuntimeError):
        bump_version.add_release_entry(result, "0.3.7", "2026-11-28", "Again")


def test_compare_detects_no_change(pack, tmp_path) -> None:
    classification, details, changed = validate_packs.compare(
        {pack.id: pack},
        {pack.id: pack},
        tmp_path / "figures",
        {},
        0.05,
    )
    assert classification == "none"
    assert details == []
    assert not changed


def test_compare_small_errata_can_release(pack, tmp_path) -> None:
    questions = list(pack.questions)
    questions[0] = replace(questions[0], text="Corrected wording")
    changed_pack = replace(pack, questions=tuple(questions))
    classification, details, changed = validate_packs.compare(
        {pack.id: changed_pack},
        {pack.id: pack},
        tmp_path / "figures",
        {},
        0.5,
    )
    assert classification == "release"
    assert changed
    assert any("questions changed" in item for item in details)


def test_compare_large_change_needs_review(pack, tmp_path) -> None:
    questions = list(pack.questions)
    questions[0] = replace(questions[0], text="Corrected wording")
    changed_pack = replace(pack, questions=tuple(questions))
    classification, _details, _changed = validate_packs.compare(
        {pack.id: changed_pack},
        {pack.id: pack},
        tmp_path / "figures",
        {},
        0.01,
    )
    assert classification == "review"


def test_compare_metadata_change_needs_review(pack, tmp_path) -> None:
    changed_pack = replace(
        pack,
        exam=replace(pack.exam, passing=pack.exam.passing + 1),
    )
    classification, _details, _changed = validate_packs.compare(
        {pack.id: changed_pack},
        {pack.id: pack},
        tmp_path / "figures",
        {},
        0.05,
    )
    assert classification == "review"


def test_compare_revision_only_can_release(pack, tmp_path) -> None:
    changed_pack = replace(
        pack,
        source=replace(pack.source, revision="new-revision"),
    )
    classification, details, changed = validate_packs.compare(
        {pack.id: changed_pack},
        {pack.id: pack},
        tmp_path / "figures",
        {},
        0.05,
    )
    assert classification == "release"
    assert changed
    assert any("revision" in item for item in details)


def test_compare_figure_change_needs_review(pack, tmp_path) -> None:
    figures = tmp_path / "figures"
    figures.mkdir()
    (figures / "T-1.png").write_bytes(b"new")
    baseline = {"src/exam_pool/resources/figures/T-1.png": b"old"}
    classification, details, changed = validate_packs.compare(
        {pack.id: pack},
        {pack.id: pack},
        figures,
        baseline,
        0.05,
    )
    assert classification == "review"
    assert changed
    assert "figure files changed" in details


def test_validate_pack_accepts_bundled_pack(pack, tmp_path) -> None:
    assert validate_packs._validate_pack(pack, tmp_path) == []
