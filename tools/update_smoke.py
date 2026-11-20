#!/usr/bin/env python3
"""Integration smoke test for the in-app update banner and download path."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from gi.repository import GLib

from exam_pool.application import ExamPoolApplication
from exam_pool.data.packs import PackRepository
from exam_pool.domain.models import pack_to_dict


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def prepare_feed() -> tuple[Path, Path]:
    root = Path(tempfile.mkdtemp(prefix="exam-pool-update-"))
    feed = root / "feed"
    data = root / "data"
    feed.mkdir()
    data.mkdir()

    pack = PackRepository().load_all()[0]
    payload = pack_to_dict(pack)
    payload["source"]["revision"] = "smoke-update"
    pack_bytes = json.dumps(payload).encode()
    (feed / "technician.json").write_bytes(pack_bytes)

    manifest = {
        "schema": 1,
        "base_url": feed.as_uri() + "/",
        "packs": [
            {
                "id": pack.id,
                "license_class": pack.license_class,
                "revision": "smoke-update",
                "path": "technician.json",
                "sha256": sha256(pack_bytes),
                "questions": len(pack.questions),
                "effective": pack.effective.isoformat(),
                "expires": pack.expires.isoformat(),
            }
        ],
        "figures": [],
    }
    (feed / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return feed / "manifest.json", data


def wait_for_banner(app: ExamPoolApplication, attempts: int = 20) -> None:
    if attempts <= 0:
        raise AssertionError("update banner did not appear")
    window = app._window
    assert window is not None
    if window._banner.get_revealed() and "update" in window._banner.get_title().lower():
        print("update banner appeared")
        window._on_banner_button(window._banner)
        GLib.timeout_add(100, wait_for_download, app, 40)
    else:
        GLib.timeout_add(100, wait_for_banner, app, attempts - 1)


def wait_for_download(app: ExamPoolApplication, attempts: int) -> None:
    if attempts <= 0:
        raise AssertionError("update download did not complete")
    window = app._window
    assert window is not None
    if "installed" in window._banner.get_title().lower():
        content = Path(os.environ["XDG_DATA_HOME"]) / "exam-pool" / "content"
        assert list((content / "packs").glob("*.json"))
        print("update downloaded and installed")
        app.quit()
        return
    GLib.timeout_add(100, wait_for_download, app, attempts - 1)


def main() -> int:
    manifest, _data = prepare_feed()
    os.environ["EXAM_POOL_UPDATE_URL"] = manifest.as_uri()
    app = ExamPoolApplication()
    app.connect(
        "activate",
        lambda application: GLib.timeout_add(100, wait_for_banner, application),
    )
    return app.run([])


if __name__ == "__main__":
    raise SystemExit(main())
