#!/usr/bin/env python3
"""Bump the application version and add an AppStream release entry."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
INIT = ROOT / "src/exam_pool/__init__.py"
MESON = ROOT / "meson.build"
METAINFO = ROOT / "data/io.github.jeangrenouille010101.Ohmwork.metainfo.xml"


def read_version() -> str:
    match = re.search(r'^version = "([^"]+)"$', PYPROJECT.read_text(), re.MULTILINE)
    if match is None:
        raise RuntimeError(f"could not read version from {PYPROJECT}")
    return match.group(1)


def next_version(version: str, part: str) -> str:
    major, minor, patch = (int(item) for item in version.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def add_release_entry(text: str, version: str, date: str, notes: str) -> str:
    marker = "  <releases>\n"
    if marker not in text:
        raise RuntimeError("metainfo file has no <releases> block")
    if f'<release version="{version}"' in text:
        raise RuntimeError(f"release {version} already exists")
    clean_notes = " ".join(notes.split())
    entry = (
        f'    <release version="{version}" date="{date}">\n'
        "      <description>\n"
        f"        <p>{escape(clean_notes)}</p>\n"
        "      </description>\n"
        "    </release>\n"
    )
    return text.replace(marker, marker + entry, 1)


def replace_versions(version: str) -> None:
    pyproject = PYPROJECT.read_text()
    pyproject = re.sub(
        r'^version = "[^"]+"$',
        f'version = "{version}"',
        pyproject,
        count=1,
        flags=re.MULTILINE,
    )
    PYPROJECT.write_text(pyproject)

    init = INIT.read_text()
    init = re.sub(
        r'^__version__ = "[^"]+"$',
        f'__version__ = "{version}"',
        init,
        count=1,
        flags=re.MULTILINE,
    )
    INIT.write_text(init)

    meson = MESON.read_text()
    meson = re.sub(
        r"version: '[^']+'",
        f"version: '{version}'",
        meson,
        count=1,
    )
    MESON.write_text(meson)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--part", choices=("major", "minor", "patch"), default="patch")
    parser.add_argument("--version")
    parser.add_argument("--date", default=datetime.now(UTC).date().isoformat())
    parser.add_argument(
        "--notes",
        default="Update the bundled NCVEC question pools.",
    )
    args = parser.parse_args()

    current = read_version()
    version = args.version or next_version(current, args.part)
    replace_versions(version)
    metainfo = METAINFO.read_text()
    METAINFO.write_text(
        add_release_entry(metainfo, version, args.date, args.notes)
    )
    print(version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
