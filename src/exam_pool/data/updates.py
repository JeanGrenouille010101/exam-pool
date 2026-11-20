from __future__ import annotations

import hashlib
import json
import os
import tempfile
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..domain.models import Pack, PackError, pack_from_dict

DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/gavins/exam-pool/main/content/manifest.json"
)


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ManifestPack:
    id: str
    license_class: str
    revision: str
    path: str
    sha256: str
    questions: int
    effective: str
    expires: str


@dataclass(frozen=True, slots=True)
class ManifestFigure:
    id: str
    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class Manifest:
    base_url: str
    packs: tuple[ManifestPack, ...]
    figures: tuple[ManifestFigure, ...]


def manifest_url() -> str:
    return os.environ.get("EXAM_POOL_UPDATE_URL", DEFAULT_MANIFEST_URL)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_url(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "ExamPool-Updater/1"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def fetch_manifest(url: str | None = None, timeout: float = 15.0) -> Manifest:
    url = url or manifest_url()
    try:
        raw = _read_url(url, timeout)
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise UpdateError(f"could not fetch update manifest: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise UpdateError("unsupported update manifest")
    base_url = data.get("base_url") or urllib.parse.urljoin(url, ".")
    packs = []
    for item in data.get("packs", []):
        try:
            packs.append(
                ManifestPack(
                    id=str(item["id"]),
                    license_class=str(item["license_class"]),
                    revision=str(item["revision"]),
                    path=str(item["path"]),
                    sha256=str(item["sha256"]),
                    questions=int(item["questions"]),
                    effective=str(item["effective"]),
                    expires=str(item["expires"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise UpdateError(f"invalid manifest pack entry: {item!r}") from exc
    figures = []
    for item in data.get("figures", []):
        try:
            figures.append(
                ManifestFigure(
                    id=str(item["id"]),
                    path=str(item["path"]),
                    sha256=str(item["sha256"]),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise UpdateError(f"invalid manifest figure entry: {item!r}") from exc
    if not packs:
        raise UpdateError("update manifest contains no packs")
    return Manifest(
        base_url=str(base_url),
        packs=tuple(packs),
        figures=tuple(figures),
    )


class ContentUpdater:
    def __init__(
        self,
        content_dir: Path,
        *,
        bundled_figure_dir: Path | None = None,
        url: str | None = None,
        timeout: float = 15.0,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self._content_dir = content_dir
        self._bundled_figure_dir = bundled_figure_dir
        self._url = url or manifest_url()
        self._timeout = timeout
        self._on_status = on_status or (lambda _message: None)
        self._pack_dir = content_dir / "packs"
        self._figure_dir = content_dir / "figures"

    def check(self, local_packs: list[Pack]) -> Manifest | None:
        manifest = fetch_manifest(self._url, self._timeout)
        local_revisions = {pack.id: pack.source.revision for pack in local_packs}
        packs = [
            item
            for item in manifest.packs
            if local_revisions.get(item.id) != item.revision
        ]
        figures = [
            item
            for item in manifest.figures
            if self._figure_is_stale(item)
        ]
        if not packs and not figures:
            return None
        return Manifest(manifest.base_url, tuple(packs), tuple(figures))

    def _figure_is_stale(self, figure: ManifestFigure) -> bool:
        for path in self._figure_candidates(figure.id):
            if path.exists():
                return _sha256(path) != figure.sha256
        return True

    def _figure_candidates(self, figure_id: str) -> tuple[Path, ...]:
        candidates = [self._figure_dir / f"{figure_id}.png"]
        if self._bundled_figure_dir is not None:
            candidates.append(self._bundled_figure_dir / f"{figure_id}.png")
        return tuple(candidates)

    def _local_figure(self, figure_id: str) -> Path:
        return self._figure_dir / f"{figure_id}.png"

    def download(self, manifest: Manifest) -> None:
        self._pack_dir.mkdir(parents=True, exist_ok=True)
        self._figure_dir.mkdir(parents=True, exist_ok=True)
        for item in manifest.packs:
            self._on_status(f"Downloading {item.id}")
            destination = self._pack_dir / f"{item.id}.json"
            self._download_verified(
                urllib.parse.urljoin(manifest.base_url, item.path),
                destination,
                item.sha256,
            )
            try:
                data = json.loads(destination.read_text(encoding="utf-8"))
                pack = pack_from_dict(data)
            except (OSError, json.JSONDecodeError, PackError) as exc:
                destination.unlink(missing_ok=True)
                raise UpdateError(f"downloaded pack {item.id} is invalid: {exc}") from exc
            if pack.id != item.id:
                destination.unlink(missing_ok=True)
                raise UpdateError(
                    f"manifest pack {item.id} contains pack {pack.id}"
                )

        for item in manifest.figures:
            self._on_status(f"Downloading figure {item.id}")
            destination = self._local_figure(item.id)
            self._download_verified(
                urllib.parse.urljoin(manifest.base_url, item.path),
                destination,
                item.sha256,
            )
        self._on_status("Update installed")

    def _download_verified(self, url: str, destination: Path, expected: str) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            dir=destination.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(_read_url(url, self._timeout))
            actual = _sha256(temporary)
            if actual != expected:
                raise UpdateError(
                    f"checksum mismatch for {url}: expected {expected}, got {actual}"
                )
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
