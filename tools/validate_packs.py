#!/usr/bin/env python3
"""Validate question packs and classify changes for automated releases.

Exit status is non-zero only for structurally invalid content. Large or
suspicious changes are reported through the ``classification`` GitHub output
so the workflow can open a review PR instead of releasing.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exam_pool.domain.models import Pack, PackError, pack_from_dict

PACK_DIR = ROOT / "src/exam_pool/resources/pools"
FIGURE_DIR = ROOT / "src/exam_pool/resources/figures"
PACK_TREE = "src/exam_pool/resources/pools"
FIGURE_TREE = "src/exam_pool/resources/figures"


class InvalidContent(RuntimeError):
    pass


def _question_signature(question) -> tuple:
    return (
        question.text,
        tuple((choice.id, choice.text) for choice in question.choices),
        question.correct,
        question.reference,
        question.figure,
    )


def _metadata(pack: Pack) -> tuple:
    return (
        pack.effective,
        pack.expires,
        pack.exam.questions,
        pack.exam.passing,
        tuple(
            (group.id, group.name, group.subelement, group.exam_questions)
            for group in pack.groups
        ),
    )


def _validate_pack(pack: Pack, figure_dir: Path) -> list[str]:
    errors: list[str] = []
    if pack.exam.questions <= 0:
        errors.append("exam question count must be positive")
    if pack.exam.passing < 0 or pack.exam.passing > pack.exam.questions:
        errors.append("passing score is outside the exam range")
    if pack.effective > pack.expires:
        errors.append("effective date is after expiry date")

    group_ids = {group.id for group in pack.groups}
    group_questions = sum(group.exam_questions for group in pack.groups)
    if group_questions != pack.exam.questions:
        errors.append(
            f"groups require {group_questions} exam questions, "
            f"expected {pack.exam.questions}"
        )

    seen: set[str] = set()
    for question in pack.questions:
        if question.id in seen:
            errors.append(f"duplicate question ID {question.id}")
        seen.add(question.id)
        if question.group not in group_ids:
            errors.append(f"{question.id} uses unknown group {question.group}")
        if not question.text.strip():
            errors.append(f"{question.id} has empty question text")
        choice_ids = tuple(choice.id for choice in question.choices)
        if choice_ids != ("A", "B", "C", "D"):
            errors.append(f"{question.id} choices are {choice_ids}, expected A-D")
        if question.correct not in choice_ids:
            errors.append(f"{question.id} correct answer is not a choice")
        if any(not choice.text.strip() for choice in question.choices):
            errors.append(f"{question.id} has an empty choice")
        if question.figure and not (figure_dir / f"{question.figure}.png").exists():
            errors.append(f"{question.id} references missing figure {question.figure}")
    return errors


def load_packs(pack_dir: Path, figure_dir: Path) -> dict[str, Pack]:
    if not pack_dir.exists():
        raise InvalidContent(f"pack directory does not exist: {pack_dir}")
    packs: dict[str, Pack] = {}
    errors: list[str] = []
    for path in sorted(pack_dir.glob("*.json")):
        if path.name == "index.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pack = pack_from_dict(data)
        except (OSError, json.JSONDecodeError, PackError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        if pack.id in packs:
            errors.append(f"duplicate pack ID {pack.id}")
        packs[pack.id] = pack
        errors.extend(f"{path.name}: {error}" for error in _validate_pack(pack, figure_dir))
    if not packs and not errors:
        errors.append(f"no question packs found in {pack_dir}")
    if errors:
        raise InvalidContent("\n".join(errors))
    return packs


def validate_index(pack_dir: Path, packs: dict[str, Pack]) -> None:
    path = pack_dir / "index.json"
    if not path.exists():
        raise InvalidContent(f"missing pack index: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidContent(f"could not read pack index: {exc}") from exc
    if data.get("schema") != 1:
        raise InvalidContent("unsupported pack index schema")
    raw_packs = data.get("packs")
    if not isinstance(raw_packs, list):
        raise InvalidContent("pack index has no packs list")
    entries = {str(item.get("id")): item for item in raw_packs}
    if set(entries) != set(packs):
        raise InvalidContent("pack index does not match the pack files")
    for pack_id, pack in packs.items():
        entry = entries[pack_id]
        expected = {
            "question_count": len(pack.questions),
            "group_count": len(pack.groups),
            "revision": pack.source.revision,
            "exam_questions": pack.exam.questions,
            "passing": pack.exam.passing,
        }
        try:
            actual = {
                "question_count": int(entry.get("question_count", -1)),
                "group_count": int(entry.get("group_count", -1)),
                "revision": str(entry.get("source", {}).get("revision")),
                "exam_questions": int(entry.get("exam", {}).get("questions", -1)),
                "passing": int(entry.get("exam", {}).get("passing", -1)),
            }
        except (TypeError, ValueError, AttributeError) as exc:
            raise InvalidContent(
                f"pack index entry for {pack_id} is malformed: {exc}"
            ) from exc
        if expected != actual:
            raise InvalidContent(
                f"pack index entry for {pack_id} is stale: "
                f"expected {expected}, found {actual}"
            )


def _git(*args: str) -> bytes:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise InvalidContent(
            result.stderr.decode("utf-8", "replace").strip()
            or f"git {' '.join(args)} failed"
        )
    return result.stdout


def load_baseline(ref: str) -> tuple[dict[str, Pack], dict[str, bytes]]:
    pack_files = _git("ls-tree", "-r", "--name-only", ref, "--", PACK_TREE)
    packs: dict[str, Pack] = {}
    for name in pack_files.decode("utf-8").splitlines():
        path = Path(name)
        if path.suffix != ".json" or path.name == "index.json":
            continue
        raw = _git("show", f"{ref}:{name}")
        try:
            pack = pack_from_dict(json.loads(raw))
        except (json.JSONDecodeError, PackError) as exc:
            raise InvalidContent(f"baseline pack {name} is invalid: {exc}") from exc
        packs[pack.id] = pack

    figure_files = _git("ls-tree", "-r", "--name-only", ref, "--", FIGURE_TREE)
    figures = {
        name: _git("show", f"{ref}:{name}")
        for name in figure_files.decode("utf-8").splitlines()
        if name.endswith(".png")
    }
    return packs, figures


def compare(
    packs: dict[str, Pack],
    baseline_packs: dict[str, Pack],
    figure_dir: Path,
    baseline_figures: dict[str, bytes],
    threshold: float,
) -> tuple[str, list[str], bool]:
    details: list[str] = []
    changed = False
    review = False

    current_ids = set(packs)
    baseline_ids = set(baseline_packs)
    if current_ids != baseline_ids:
        changed = True
        review = True
        added = sorted(current_ids - baseline_ids)
        removed = sorted(baseline_ids - current_ids)
        if added:
            details.append(f"new packs: {', '.join(added)}")
        if removed:
            details.append(f"removed packs: {', '.join(removed)}")

    for pack_id in sorted(current_ids & baseline_ids):
        current = packs[pack_id]
        baseline = baseline_packs[pack_id]
        if current.source.revision != baseline.source.revision:
            changed = True
            details.append(
                f"{pack_id}: revision {baseline.source.revision} "
                f"-> {current.source.revision}"
            )
        if _metadata(current) != _metadata(baseline):
            changed = True
            review = True
            details.append(f"{pack_id}: pack/groups/exam metadata changed")

        current_questions = {q.id: q for q in current.questions}
        baseline_questions = {q.id: q for q in baseline.questions}
        changed_questions = 0
        for question_id in set(current_questions) | set(baseline_questions):
            if (
                question_id not in current_questions
                or question_id not in baseline_questions
                or _question_signature(current_questions[question_id])
                != _question_signature(baseline_questions[question_id])
            ):
                changed_questions += 1
        denominator = max(len(current_questions), len(baseline_questions), 1)
        ratio = changed_questions / denominator
        if changed_questions:
            changed = True
            details.append(
                f"{pack_id}: {changed_questions}/{denominator} questions changed "
                f"({ratio:.1%})"
            )
        if ratio > threshold:
            review = True

    current_figures = {}
    if figure_dir.exists():
        for path in sorted(figure_dir.glob("*.png")):
            name = f"{FIGURE_TREE}/{path.name}"
            current_figures[name] = path.read_bytes()
    if current_figures != baseline_figures:
        changed = True
        review = True
        details.append("figure files changed")

    if not changed:
        return "none", details, False
    return ("review" if review else "release"), details, True


def write_outputs(values: dict[str, str], github_output: str | None) -> None:
    path = github_output or os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as handle:
        handle.writelines(f"{key}={value}\n" for key, value in values.items())


def pack_summary(packs: dict[str, Pack]) -> list[str]:
    lines = []
    for pack_id in sorted(packs):
        pack = packs[pack_id]
        lines.append(
            f"- {pack_id}: {len(pack.questions)} questions, "
            f"revision {pack.source.revision}"
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-dir", type=Path, default=PACK_DIR)
    parser.add_argument("--figure-dir", type=Path, default=FIGURE_DIR)
    parser.add_argument("--baseline-ref", default="HEAD")
    parser.add_argument("--released-ref", default="")
    parser.add_argument("--threshold", type=float, default=0.05)
    parser.add_argument("--github-output")
    parser.add_argument("--summary")
    args = parser.parse_args()

    lines = ["# Question pool validation", ""]
    details: list[str] = []
    try:
        packs = load_packs(args.pack_dir, args.figure_dir)
        validate_index(args.pack_dir, packs)
        lines.extend(["## Packs", "", *pack_summary(packs), ""])
    except InvalidContent as exc:
        message = f"Invalid content:\n{exc}"
        print(message, file=sys.stderr)
        lines.extend(["## Invalid content", "", "```", str(exc), "```"])
        write_outputs(
            {"classification": "invalid", "changed": "true"}, args.github_output
        )
        _write_summary(args.summary, lines)
        return 1

    if not args.baseline_ref:
        classification = "release"
        changed = True
        lines.extend(["## Baseline", "", "Baseline comparison skipped.", ""])
    else:
        try:
            baseline_packs, baseline_figures = load_baseline(args.baseline_ref)
            classification, details, changed = compare(
                packs,
                baseline_packs,
                args.figure_dir,
                baseline_figures,
                args.threshold,
            )
        except InvalidContent as exc:
            print(f"Could not compare baseline: {exc}", file=sys.stderr)
            classification = "review"
            changed = True
            details = [f"baseline comparison failed: {exc}"]

    if classification == "none" and args.released_ref:
        try:
            released_packs, released_figures = load_baseline(args.released_ref)
            _, released_details, released_changed = compare(
                packs,
                released_packs,
                args.figure_dir,
                released_figures,
                args.threshold,
            )
        except InvalidContent as exc:
            print(f"Could not compare last release: {exc}", file=sys.stderr)
            classification = "review"
            changed = True
            details.append(f"release comparison failed: {exc}")
        else:
            if released_changed:
                classification = "release"
                changed = True
                details.append(
                    f"content differs from last release {args.released_ref}"
                )
                details.extend(released_details)

    if args.baseline_ref:
        lines.extend(["## Changes", ""])
        lines.extend(f"- {item}" for item in details)
        if not details:
            lines.append("- No content changes detected.")
        lines.append("")

    lines.extend(
        [
            "## Classification",
            "",
            f"`{classification}`",
            "",
        ]
    )
    print("\n".join(lines))
    _write_summary(args.summary, lines)
    write_outputs(
        {
            "classification": classification,
            "changed": "true" if changed else "false",
        },
        args.github_output,
    )
    return 0


def _write_summary(path: str | None, lines: list[str]) -> None:
    if path:
        Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
