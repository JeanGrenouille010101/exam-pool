#!/usr/bin/env python3
"""Build the lightweight pool index used at application startup."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from exam_pool.domain.models import pack_from_dict, pack_summary

DEFAULT_PACKS = ROOT / "src" / "exam_pool" / "resources" / "pools"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packs", type=Path, default=DEFAULT_PACKS)
    args = parser.parse_args()

    packs = []
    for path in sorted(args.packs.glob("*.json")):
        if path.name == "index.json":
            continue
        pack = pack_from_dict(json.loads(path.read_text(encoding="utf-8")))
        summary = pack_summary(pack)
        packs.append(
            {
                "id": summary.id,
                "country": summary.country,
                "country_name": summary.country_name,
                "license_class": summary.license_class,
                "license_name": summary.license_name,
                "element": summary.element,
                "effective": summary.effective.isoformat(),
                "expires": summary.expires.isoformat(),
                "source": {
                    "name": summary.source.name,
                    "url": summary.source.url,
                    "revision": summary.source.revision,
                    "license": summary.source.license,
                },
                "exam": {
                    "questions": summary.exam.questions,
                    "passing": summary.exam.passing,
                },
                "question_count": summary.question_count,
                "group_count": summary.group_count,
            }
        )
    destination = args.packs / "index.json"
    destination.write_text(
        json.dumps({"schema": 1, "packs": packs}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {destination} ({len(packs)} packs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
