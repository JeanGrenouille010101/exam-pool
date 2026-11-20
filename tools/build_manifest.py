#!/usr/bin/env python3
"""Create the update manifest for the bundled NCVEC content."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PACKS = ROOT / "src" / "exam_pool" / "resources" / "pools"
DEFAULT_FIGURES = ROOT / "src" / "exam_pool" / "resources" / "figures"
DEFAULT_OUTPUT = ROOT / "content" / "manifest.json"
DEFAULT_BASE_URL = "https://raw.githubusercontent.com/JeanGrenouille010101/exam-pool/main/"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packs", type=Path, default=DEFAULT_PACKS)
    parser.add_argument("--figures", type=Path, default=DEFAULT_FIGURES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    args = parser.parse_args()

    packs = []
    for path in sorted(args.packs.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        packs.append(
            {
                "id": data["id"],
                "license_class": data["license_class"],
                "revision": data["source"]["revision"],
                "path": relative(path),
                "sha256": sha256(path),
                "questions": len(data["questions"]),
                "effective": data["effective"],
                "expires": data["expires"],
            }
        )

    figures = [
        {
            "id": path.stem,
            "path": relative(path),
            "sha256": sha256(path),
        }
        for path in sorted(args.figures.glob("*.png"))
    ]

    manifest = {
        "schema": 1,
        "base_url": args.base_url,
        "packs": packs,
        "figures": figures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {args.output} ({len(packs)} packs, {len(figures)} figures)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
