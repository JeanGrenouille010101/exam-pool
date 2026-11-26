#!/usr/bin/env python3
"""Build the bundled question packs from the official NCVEC PDFs.

This is a maintainer tool, not part of the installed application. It requires
`pdftotext`, `pdftoppm`, and Pillow. The generated JSON packs and figure PNGs
are committed so the application remains offline-first.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE = ROOT / ".sources"
DEFAULT_PACK_DIR = ROOT / "src" / "exam_pool" / "resources" / "pools"
DEFAULT_FIGURE_DIR = ROOT / "src" / "exam_pool" / "resources" / "figures"


@dataclass(frozen=True)
class PoolSource:
    slug: str
    pack_id: str
    license_class: str
    license_name: str
    element: int
    effective: date
    expires: date
    exam_questions: int
    passing: int
    revision: str
    pool_url: str
    figures_url: str
    figures_kind: str


SOURCES = (
    PoolSource(
        slug="technician",
        pack_id="us-technician-2026",
        license_class="technician",
        license_name="Technician",
        element=2,
        effective=date(2026, 7, 1),
        expires=date(2030, 6, 30),
        exam_questions=35,
        passing=26,
        revision="2026-02-19",
        pool_url=(
            "https://ncvec.org/downloads/2026-2030%20Technician%20Pool%20and%20"
            "Syllabus%20Public%20Release%20Feb%2019%202026.pdf"
        ),
        figures_url=(
            "https://ncvec.org/downloads/TECH_2026/"
            "2026-2030%20Technician%20Pool%203%20Diagrams.pdf"
        ),
        figures_kind="tech",
    ),
    PoolSource(
        slug="general",
        pack_id="us-general-2023",
        license_class="general",
        license_name="General",
        element=3,
        effective=date(2023, 7, 1),
        expires=date(2027, 6, 30),
        exam_questions=35,
        passing=26,
        revision="2026-02-04",
        pool_url=(
            "https://ncvec.org/downloads/General%20Class%20Pool%20and%20"
            "Syllabus%202023-2027%20Public%20Release%20with%206th%20Errata%20"
            "Feb%204%202026.pdf"
        ),
        figures_url="https://www.ncvec.org/downloads/G7-1.pdf",
        figures_kind="general",
    ),
    PoolSource(
        slug="extra",
        pack_id="us-extra-2024",
        license_class="extra",
        license_name="Amateur Extra",
        element=4,
        effective=date(2024, 7, 1),
        expires=date(2028, 6, 30),
        exam_questions=50,
        passing=37,
        revision="2026-02-04",
        pool_url=(
            "https://ncvec.org/downloads/2024-2028%20Extra%20Class%20Question%20"
            "Pool%20and%20Syllabus%20Public%20Release%20with%204th%20Errata%20"
            "Feb%204%202026.pdf"
        ),
        figures_url=(
            "https://www.ncvec.org/downloads/Extra_Figures_2024-2028-1.pdf"
        ),
        figures_kind="extra",
    ),
)

QUESTION_ID = re.compile(r"^([TGE]\d[A-Z]\d{2})\s+\(([A-D])\)(?:\s*\[([^\]]+)\])?\s*$")
DELETED = re.compile(r"^([TGE]\d[A-Z]\d{2})\s+Question Deleted")
CHOICE = re.compile(r"^([A-D])\.\s*(.*)$")
SUBELEMENT = re.compile(
    r"^SUBELEMENT\s+([TGE]\d+)\s*[-–]\s*(.+?)\s*"
    r"\[(\d+)\s+Exam Questions?\s*[-–]\s*(\d+)\s+Groups?\]"
    r"(?:\s+\d+\s+Questions?)?\s*$",
    re.IGNORECASE,
)
GROUP_HEADER = re.compile(r"^([TGE]\d[A-Z])(?:\s*[-–]\s*|\s+)(.+)$")
PAGE_NOISE = re.compile(
    r"^(?:"
    r"\d{4}-\d{4}\s+(?:Technician|General|Extra).*"
    r"|FCC Element\s+\d+.*"
    r"|Effective\s+.*"
    r"|SUBELEMENT\s+.*"
    r"|Question Pool.*"
    r"|.*Question Pool Errata.*"
    r"|.*Errata\s*$"
    r"|Issued\s+.*"
    r"|Released\s+.*"
    r"|The following changes.*"
    r"|\d+\s*$"
    r")",
    re.IGNORECASE,
)
FIGURE = re.compile(r"\b(?:figure|diagram)\s+([TGE]\d*-\d+)\b", re.IGNORECASE)


class ImportError_(RuntimeError):
    pass


def run(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)


def download(url: str, destination: Path, refresh: bool) -> None:
    if destination.exists() and not refresh:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"download {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "ExamPool-Importer/1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read()
    if not data.startswith(b"%PDF"):
        raise ImportError_(f"{url} did not return a PDF")
    destination.write_bytes(data)


def extract_text(pdf: Path, text_path: Path, refresh: bool) -> str:
    if refresh or not text_path.exists():
        run(["pdftotext", "-layout", str(pdf), str(text_path)])
    return text_path.read_text(encoding="utf-8")


def clean_line(line: str) -> str:
    return line.replace("\f", "").replace("\u00ad", "").strip()


def collapse(lines: list[str]) -> str:
    return re.sub(r"\s+", " ", " ".join(line.strip() for line in lines)).strip()


def actual_pool_text(text: str) -> str:
    """Remove errata and syllabus, keeping only the final question pool."""
    matches = list(
        re.finditer(r"FCC Element\s+\d+\s+Question Pool\s*$", text, re.MULTILINE)
    )
    if not matches:
        raise ImportError_("could not find the question pool section")
    start = matches[-1].start()
    subelement = re.search(r"^SUBELEMENT\s+", text[start:], re.MULTILINE)
    if not subelement:
        raise ImportError_("could not find the first subelement")
    return text[start + subelement.start() :]


def syllabus_text(text: str) -> str:
    matches = list(
        re.finditer(
            r"FCC Element\s+\d+\s+Question Pool\s+Syllabus\s*$",
            text,
            re.MULTILINE,
        )
    )
    if not matches:
        raise ImportError_("could not find the syllabus section")
    start = matches[-1].end()
    pool = re.search(r"FCC Element\s+\d+\s+Question Pool\s*$", text[start:], re.MULTILINE)
    if not pool:
        raise ImportError_("could not find the end of the syllabus")
    return text[start : start + pool.start()]


def parse_groups(text: str) -> list[dict]:
    section = syllabus_text(text)
    lines = [clean_line(line) for line in section.splitlines()]
    groups: list[dict] = []
    current_subelement: str | None = None
    subelement_exam_questions = 0
    subelement_group_count = 0
    current_group: dict | None = None
    description: list[str] = []

    def finish_group() -> None:
        nonlocal current_group, description
        if current_group is None:
            return
        current_group["name"] = collapse(description) or current_group["id"]
        groups.append(current_group)
        current_group = None
        description = []

    def finish_subelement() -> None:
        nonlocal subelement_exam_questions, subelement_group_count
        finish_group()
        if current_subelement is None:
            return
        if subelement_exam_questions != subelement_group_count:
            raise ImportError_(
                f"{current_subelement}: {subelement_group_count} groups but "
                f"{subelement_exam_questions} exam questions"
            )
        subelement_exam_questions = 0
        subelement_group_count = 0

    for line in lines:
        if not line:
            finish_group()
            continue
        sub = SUBELEMENT.match(line)
        if sub:
            finish_subelement()
            current_subelement = sub.group(1)
            subelement_exam_questions = int(sub.group(3))
            subelement_group_count = int(sub.group(4))
            continue
        if PAGE_NOISE.match(line):
            continue
        group = GROUP_HEADER.match(line)
        if group and current_subelement and not re.match(
            r"^[TGE]\d[A-Z]\d{2}\b", line
        ):
            finish_group()
            current_group = {
                "id": group.group(1),
                "name": "",
                "subelement": current_subelement,
                "exam_questions": 1,
            }
            description = [group.group(2)]
            continue
        if current_group is not None:
            description.append(line)

    finish_subelement()
    if not groups:
        raise ImportError_("no syllabus groups parsed")
    return groups


def parse_questions(text: str, slug: str) -> list[dict]:
    pool = actual_pool_text(text)
    blocks = re.split(r"^\s*~~\s*$", pool, flags=re.MULTILINE)
    questions: list[dict] = []
    problems: list[str] = []

    for block in blocks:
        raw_lines = [clean_line(line) for line in block.splitlines()]
        lines = [
            line
            for line in raw_lines
            if line and not PAGE_NOISE.match(line)
        ]
        header_index = None
        for index, line in enumerate(lines):
            if QUESTION_ID.match(line):
                header_index = index
                break
            if DELETED.match(line):
                break
        if header_index is None:
            continue

        match = QUESTION_ID.match(lines[header_index])
        assert match is not None
        question_id, correct, reference = match.groups()
        body = lines[header_index + 1 :]
        choice_start = next(
            (index for index, line in enumerate(body) if CHOICE.match(line)),
            None,
        )
        if choice_start is None:
            problems.append(f"{question_id}: no choices")
            continue

        question_text = collapse(body[:choice_start])
        choices: dict[str, str] = {}
        current_choice: str | None = None
        for line in body[choice_start:]:
            choice_match = CHOICE.match(line)
            if choice_match:
                current_choice = choice_match.group(1)
                choices[current_choice] = choice_match.group(2).strip()
            elif current_choice is not None:
                choices[current_choice] = collapse(
                    [choices[current_choice], line]
                )
        if set(choices) != set("ABCD"):
            problems.append(f"{question_id}: choices are {sorted(choices)}")
            continue
        if not question_text:
            problems.append(f"{question_id}: empty question")
            continue

        figure_match = FIGURE.search(question_text)
        figure = figure_match.group(1).upper() if figure_match else None
        questions.append(
            {
                "id": question_id,
                "group": question_id[:3],
                "text": question_text,
                "choices": [
                    {"id": choice_id, "text": choices[choice_id]}
                    for choice_id in "ABCD"
                ],
                "correct": correct,
                "reference": reference,
                "figure": figure,
            }
        )

    if problems:
        raise ImportError_(f"{slug}: question parse problems:\n" + "\n".join(problems))
    if not questions:
        raise ImportError_(f"{slug}: no questions parsed")
    return questions


def validate_questions(
    source: PoolSource,
    groups: list[dict],
    questions: list[dict],
) -> None:
    group_ids = {group["id"] for group in groups}
    if len(group_ids) != len(groups):
        raise ImportError_(f"{source.slug}: duplicate group IDs")

    ids = [question["id"] for question in questions]
    if len(ids) != len(set(ids)):
        raise ImportError_(f"{source.slug}: duplicate question IDs")

    for question in questions:
        if question["group"] not in group_ids:
            raise ImportError_(
                f"{source.slug}: {question['id']} has unknown group "
                f"{question['group']}"
            )
        if len(question["choices"]) != 4:
            raise ImportError_(f"{source.slug}: {question['id']} needs four choices")
        if question["correct"] not in {choice["id"] for choice in question["choices"]}:
            raise ImportError_(
                f"{source.slug}: {question['id']} has an invalid correct answer"
            )

    counts: dict[str, int] = {group_id: 0 for group_id in group_ids}
    for question in questions:
        counts[question["group"]] += 1
    for group in groups:
        if counts[group["id"]] < group["exam_questions"]:
            raise ImportError_(
                f"{source.slug}: group {group['id']} has too few questions"
            )

    exam_total = sum(group["exam_questions"] for group in groups)
    if exam_total != source.exam_questions:
        raise ImportError_(
            f"{source.slug}: groups provide {exam_total} exam questions, "
            f"expected {source.exam_questions}"
        )

    figures = {question["figure"] for question in questions if question["figure"]}
    missing = figures - figure_ids()
    if missing:
        raise ImportError_(
            f"{source.slug}: missing figure images: {', '.join(sorted(missing))}"
        )


def figure_ids() -> set[str]:
    names = set()
    for name in ("T-1", "T-2", "T-3", "G7-1"):
        names.add(name)
    names.update(
        f"E{number}-{index}"
        for number, count in ((5, 1), (6, 3), (7, 3), (9, 3))
        for index in range(1, count + 1)
    )
    return names


def _trimmed(image: Image.Image) -> Image.Image:
    image = image.convert("RGB")
    background = Image.new("RGB", image.size, (255, 255, 255))
    difference = ImageChops.difference(image, background)
    bbox = difference.getbbox()
    if not bbox:
        return image
    left, top, right, bottom = bbox
    padding = 16
    bbox = (
        max(0, left - padding),
        max(0, top - padding),
        min(image.width, right + padding),
        min(image.height, bottom + padding),
    )
    return image.crop(bbox)


def _same_pixels(path: Path, image: Image.Image) -> bool:
    if not path.exists():
        return False
    try:
        existing = Image.open(path).convert("RGB")
    except OSError:
        return False
    return existing.size == image.size and existing.tobytes() == image.tobytes()


def save_figure(image: Image.Image, destination: Path) -> None:
    """Write a figure only when its pixels changed.

    PNG encoders and PDF renderers can produce different bytes for identical
    artwork, which used to create noise in every scheduled import.
    """
    image = _trimmed(image)
    if _same_pixels(destination, image):
        return
    image.save(destination, "PNG", optimize=True)


def render_pages(pdf: Path, output_dir: Path, refresh: bool) -> list[Path]:
    render_dir = output_dir / f".render-{pdf.stem}"
    if render_dir.exists():
        shutil.rmtree(render_dir)
    render_dir.mkdir(parents=True)
    prefix = render_dir / "page"
    run(["pdftoppm", "-png", "-r", "180", str(pdf), str(prefix)])
    return sorted(render_dir.glob("*.png"))


def render_figures(
    source: PoolSource,
    pdf: Path,
    output_dir: Path,
    refresh: bool,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    if source.figures_kind == "tech":
        expected = [output_dir / f"{figure_id}.png" for figure_id in ("T-1", "T-2", "T-3")]
        if all(path.exists() for path in expected) and not refresh:
            return
        pages = render_pages(pdf, output_dir, refresh)
        if len(pages) != 3:
            raise ImportError_(f"{source.slug}: expected 3 diagram pages")
        for page, figure_id in zip(pages, ("T-1", "T-2", "T-3")):
            save_figure(
                Image.open(page).convert("RGB"),
                output_dir / f"{figure_id}.png",
            )
            page.unlink()
        return

    if source.figures_kind == "general":
        expected = output_dir / "G7-1.png"
        if expected.exists() and not refresh:
            return
        pages = render_pages(pdf, output_dir, refresh)
        if len(pages) != 1:
            raise ImportError_(f"{source.slug}: expected 1 diagram page")
        save_figure(Image.open(pages[0]).convert("RGB"), expected)
        pages[0].unlink()
        return

    if source.figures_kind == "extra":
        expected = [
            output_dir / f"{figure_id}.png"
            for figure_id in (
                "E5-1", "E6-1", "E6-2", "E6-3",
                "E7-1", "E7-2", "E7-3",
                "E9-1", "E9-2", "E9-3",
            )
        ]
        if all(path.exists() for path in expected) and not refresh:
            return
        pages = render_pages(pdf, output_dir, refresh)
        if len(pages) != 3:
            raise ImportError_(f"{source.slug}: expected 3 diagram pages")
        crops = {
            0: (
                ("E5-1", (0.03, 0.13, 0.49, 0.55)),
                ("E6-1", (0.51, 0.13, 0.97, 0.55)),
                ("E6-2", (0.03, 0.60, 0.49, 0.93)),
                ("E6-3", (0.51, 0.60, 0.97, 0.93)),
            ),
            1: (
                ("E7-1", (0.03, 0.13, 0.49, 0.55)),
                ("E7-2", (0.51, 0.13, 0.97, 0.55)),
                ("E7-3", (0.03, 0.60, 0.49, 0.93)),
            ),
            2: (
                ("E9-1", (0.03, 0.13, 0.49, 0.55)),
                ("E9-2", (0.51, 0.13, 0.97, 0.55)),
                ("E9-3", (0.03, 0.60, 0.49, 0.96)),
            ),
        }
        for page_index, page in enumerate(pages):
            image = Image.open(page).convert("RGB")
            for figure_id, fractions in crops[page_index]:
                box = (
                    int(image.width * fractions[0]),
                    int(image.height * fractions[1]),
                    int(image.width * fractions[2]),
                    int(image.height * fractions[3]),
                )
                save_figure(
                    image.crop(box),
                    output_dir / f"{figure_id}.png",
                )
            page.unlink()
        return

    raise ImportError_(f"{source.slug}: unknown figure kind")


def build_pack(source: PoolSource, text: str, questions: list[dict], groups: list[dict]):
    return {
        "schema": 1,
        "id": source.pack_id,
        "country": "US",
        "country_name": "United States",
        "license_class": source.license_class,
        "license_name": source.license_name,
        "element": source.element,
        "effective": source.effective.isoformat(),
        "expires": source.expires.isoformat(),
        "source": {
            "name": "NCVEC Question Pool Committee",
            "url": source.pool_url,
            "revision": source.revision,
            "license": "Public domain",
        },
        "exam": {
            "questions": source.exam_questions,
            "passing": source.passing,
        },
        "groups": groups,
        "questions": questions,
    }


def write_pack(source: PoolSource, pack: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"{source.slug}.json"
    destination.write_text(
        json.dumps(pack, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="redownload sources")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--packs", type=Path, default=DEFAULT_PACK_DIR)
    parser.add_argument("--figures", type=Path, default=DEFAULT_FIGURE_DIR)
    args = parser.parse_args()

    required = ("pdftotext", "pdftoppm")
    missing = [name for name in required if shutil.which(name) is None]
    if missing:
        raise SystemExit(f"missing required tools: {', '.join(missing)}")

    args.cache.mkdir(parents=True, exist_ok=True)
    for source in SOURCES:
        pdf = args.cache / f"{source.slug}.pdf"
        text_path = args.cache / f"{source.slug}.txt"
        figures_pdf = args.cache / f"{source.slug}-figures.pdf"
        download(source.pool_url, pdf, args.refresh)
        download(source.figures_url, figures_pdf, args.refresh)
        text = extract_text(pdf, text_path, args.refresh)
        groups = parse_groups(text)
        questions = parse_questions(text, source.slug)
        validate_questions(source, groups, questions)
        pack = build_pack(source, text, questions, groups)
        destination = write_pack(source, pack, args.packs)
        render_figures(source, figures_pdf, args.figures, args.refresh)
        print(
            f"{source.license_name}: {len(questions)} questions, "
            f"{len(groups)} groups, exam {source.exam_questions}, "
            f"-> {destination.relative_to(ROOT)}"
        )

    print(f"figures -> {args.figures.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
