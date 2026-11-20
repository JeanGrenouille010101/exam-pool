from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from ..domain.models import (
    Pack,
    PackError,
    PackSummary,
    pack_from_dict,
    pack_summary,
    pack_summary_from_dict,
)


@dataclass(frozen=True, slots=True)
class PackRepository:
    pack_dir: Path | None = None
    figure_dir: Path | None = None
    user_pack_dir: Path | None = None
    user_figure_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.pack_dir is None:
            object.__setattr__(
                self, "pack_dir", Path(str(files("exam_pool").joinpath("resources/pools")))
            )
        if self.figure_dir is None:
            object.__setattr__(
                self,
                "figure_dir",
                Path(str(files("exam_pool").joinpath("resources/figures"))),
            )

    def load_summaries(self) -> list[PackSummary]:
        if not self.pack_dir or not self.pack_dir.exists():
            raise PackError(f"pack directory does not exist: {self.pack_dir}")
        index_path = self.pack_dir / "index.json"
        summaries: dict[str, PackSummary] = {}
        if index_path.exists():
            try:
                data = json.loads(index_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise PackError(f"could not read pack index {index_path}: {exc}") from exc
            if data.get("schema") != 1:
                raise PackError("unsupported pack index schema")
            for item in data.get("packs", []):
                summary = pack_summary_from_dict(item)
                summaries[summary.id] = summary
        else:
            for pack in self.load_all():
                summary = pack_summary(pack)
                summaries[summary.id] = summary
        if self.user_pack_dir and self.user_pack_dir.exists():
            for path in sorted(self.user_pack_dir.glob("*.json")):
                pack = self.load(path)
                summary = pack_summary(pack)
                summaries[summary.id] = summary
        if not summaries:
            raise PackError(f"no question packs found in {self.pack_dir}")
        order = {"technician": 0, "general": 1, "extra": 2}
        return sorted(
            summaries.values(),
            key=lambda item: (
                item.country,
                order.get(item.license_class, 99),
                item.id,
            ),
        )

    def load_pack(self, pack: PackSummary | Pack | str) -> Pack:
        pack_id = pack.id if not isinstance(pack, str) else pack
        license_class = getattr(pack, "license_class", None)
        candidates = []
        if self.user_pack_dir is not None:
            candidates.append(self.user_pack_dir / f"{pack_id}.json")
        if license_class:
            candidates.append(self.pack_dir / f"{license_class}.json")
        candidates.append(self.pack_dir / f"{pack_id}.json")
        for path in candidates:
            if path.exists():
                return self.load(path)
        raise PackError(f"question pack not found: {pack_id}")

    def load_all(self) -> list[Pack]:
        if not self.pack_dir or not self.pack_dir.exists():
            raise PackError(f"pack directory does not exist: {self.pack_dir}")
        packs_by_id: dict[str, Pack] = {}
        for directory in (self.pack_dir, self.user_pack_dir):
            if directory is None or not directory.exists():
                continue
            for path in sorted(directory.glob("*.json")):
                if path.name == "index.json":
                    continue
                pack = self.load(path)
                packs_by_id[pack.id] = pack
        if not packs_by_id:
            raise PackError(f"no question packs found in {self.pack_dir}")
        order = {"technician": 0, "general": 1, "extra": 2}
        return sorted(
            packs_by_id.values(),
            key=lambda pack: (pack.country, order.get(pack.license_class, 99), pack.id),
        )

    def load(self, path: Path) -> Pack:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PackError(f"could not read pack {path}: {exc}") from exc
        return pack_from_dict(data)

    def pack_file(self, pack: Pack | PackSummary) -> Path | None:
        candidates = []
        if self.user_pack_dir is not None:
            candidates.append(self.user_pack_dir / f"{pack.id}.json")
            candidates.append(self.user_pack_dir / f"{pack.license_class}.json")
        candidates.append(self.pack_dir / f"{pack.license_class}.json")
        candidates.append(self.pack_dir / f"{pack.id}.json")
        return next((path for path in candidates if path.exists()), None)

    def figure_path(self, figure_id: str | None) -> Path | None:
        if not figure_id:
            return None
        for directory in (self.user_figure_dir, self.figure_dir):
            if directory is not None:
                path = directory / f"{figure_id}.png"
                if path.exists():
                    return path
        return None
