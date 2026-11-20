from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from ..domain.models import Pack, PackError, pack_from_dict


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

    def load_all(self) -> list[Pack]:
        if not self.pack_dir or not self.pack_dir.exists():
            raise PackError(f"pack directory does not exist: {self.pack_dir}")
        packs_by_id: dict[str, Pack] = {}
        for directory in (self.pack_dir, self.user_pack_dir):
            if directory is None or not directory.exists():
                continue
            for path in sorted(directory.glob("*.json")):
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

    def figure_path(self, figure_id: str | None) -> Path | None:
        if not figure_id:
            return None
        for directory in (self.user_figure_dir, self.figure_dir):
            if directory is not None:
                path = directory / f"{figure_id}.png"
                if path.exists():
                    return path
        return None
