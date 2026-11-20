from __future__ import annotations

import os
from pathlib import Path


def _xdg_dir(env_name: str, fallback: str) -> Path:
    raw = os.environ.get(env_name)
    return Path(raw) if raw else Path.home() / fallback


def data_dir() -> Path:
    return _xdg_dir("XDG_DATA_HOME", ".local/share") / "exam-pool"


def database_path() -> Path:
    return data_dir() / "progress.db"


def content_dir() -> Path:
    return data_dir() / "content"
