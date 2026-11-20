from __future__ import annotations

import json
from hashlib import sha256

import pytest

from exam_pool.data.packs import PackRepository
from exam_pool.data.updates import ContentUpdater, UpdateError, fetch_manifest
from exam_pool.domain.models import pack_to_dict


def write_manifest(tmp_path, pack_payload: dict, pack_bytes: bytes, figure_bytes: bytes, revision: str = "new-revision"):
    packs_dir = tmp_path / "packs"
    figures_dir = tmp_path / "figures"
    packs_dir.mkdir()
    figures_dir.mkdir()
    (packs_dir / "technician.json").write_bytes(pack_bytes)
    (figures_dir / "T-1.png").write_bytes(figure_bytes)
    manifest = {
        "schema": 1,
        "base_url": tmp_path.as_uri() + "/",
        "packs": [
            {
                "id": pack_payload["id"],
                "license_class": pack_payload["license_class"],
                "revision": revision,
                "path": "packs/technician.json",
                "sha256": sha256(pack_bytes).hexdigest(),
                "questions": len(pack_payload["questions"]),
                "effective": pack_payload["effective"],
                "expires": pack_payload["expires"],
            }
        ],
        "figures": [
            {
                "id": "T-1",
                "path": "figures/T-1.png",
                "sha256": sha256(figure_bytes).hexdigest(),
            }
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def test_manifest_and_download_from_file_url(tmp_path, pack) -> None:
    payload = pack_to_dict(pack)
    payload["source"]["revision"] = "new-revision"
    pack_bytes = json.dumps(payload).encode()
    figure_bytes = b"not-a-real-png-but-verifiable"
    manifest_path = write_manifest(tmp_path, payload, pack_bytes, figure_bytes)

    manifest = fetch_manifest(manifest_path.as_uri())
    assert manifest.packs[0].revision == "new-revision"

    updater = ContentUpdater(
        tmp_path / "content",
        bundled_figure_dir=tmp_path / "bundled-figures",
        url=manifest_path.as_uri(),
    )
    update = updater.check([pack])
    assert update is not None
    assert [item.id for item in update.packs] == [pack.id]
    assert [item.id for item in update.figures] == ["T-1"]

    updater.download(update)
    installed = tmp_path / "content" / "packs" / f"{pack.id}.json"
    assert installed.exists()
    assert (tmp_path / "content" / "figures" / "T-1.png").read_bytes() == figure_bytes

    repository = PackRepository(
        user_pack_dir=tmp_path / "content" / "packs",
        user_figure_dir=tmp_path / "content" / "figures",
    )
    loaded = {item.id: item for item in repository.load_all()}
    assert loaded[pack.id].source.revision == "new-revision"
    assert repository.figure_path("T-1") == tmp_path / "content" / "figures" / "T-1.png"


def test_no_update_when_revisions_and_figures_match(tmp_path, pack) -> None:
    payload = pack_to_dict(pack)
    pack_bytes = json.dumps(payload).encode()
    figure_bytes = b"figure"
    manifest_path = write_manifest(tmp_path, payload, pack_bytes, figure_bytes, revision="test")
    bundled_figures = tmp_path / "bundled-figures"
    bundled_figures.mkdir()
    (bundled_figures / "T-1.png").write_bytes(figure_bytes)

    updater = ContentUpdater(
        tmp_path / "content",
        bundled_figure_dir=bundled_figures,
        url=manifest_path.as_uri(),
    )
    assert updater.check([pack]) is None


def test_changed_hash_triggers_update_even_with_same_revision(tmp_path, pack) -> None:
    payload = pack_to_dict(pack)
    pack_bytes = json.dumps(payload).encode()
    manifest_path = write_manifest(
        tmp_path, payload, pack_bytes, b"figure", revision="test"
    )
    local_path = tmp_path / "local-technician.json"
    local_path.write_bytes(b"{}")
    bundled_figures = tmp_path / "bundled-figures"
    bundled_figures.mkdir()
    (bundled_figures / "T-1.png").write_bytes(b"figure")

    updater = ContentUpdater(
        tmp_path / "content",
        bundled_figure_dir=bundled_figures,
        url=manifest_path.as_uri(),
    )
    update = updater.check([pack], local_pack_paths={pack.id: local_path})
    assert update is not None
    assert [item.id for item in update.packs] == [pack.id]


def test_checksum_mismatch_is_rejected(tmp_path, pack) -> None:
    payload = pack_to_dict(pack)
    pack_bytes = json.dumps(payload).encode()
    manifest_path = write_manifest(tmp_path, payload, pack_bytes, b"figure")
    manifest = fetch_manifest(manifest_path.as_uri())
    broken = type(manifest)(
        manifest.base_url,
        tuple(
            type(item)(
                item.id,
                item.license_class,
                item.revision,
                item.path,
                "0" * 64,
                item.questions,
                item.effective,
                item.expires,
            )
            for item in manifest.packs
        ),
        (),
    )
    updater = ContentUpdater(
        tmp_path / "content",
        url=manifest_path.as_uri(),
    )
    with pytest.raises(UpdateError):
        updater.download(broken)
