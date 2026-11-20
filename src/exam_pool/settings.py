from __future__ import annotations

from gi.repository import Gio, GLib

from . import APP_ID
from .domain.models import MasteryConfig


class Settings:
    """Small wrapper around GSettings with a safe development fallback."""

    def __init__(self) -> None:
        self._settings: Gio.Settings | None
        try:
            self._settings = Gio.Settings.new(APP_ID)
        except GLib.Error:
            self._settings = None
        self._fallback: dict[str, object] = {}

    @property
    def has_schema(self) -> bool:
        return self._settings is not None

    def _get(self, key: str, default):
        if self._settings is not None:
            return self._settings.get_value(key).unpack()
        return self._fallback.get(key, default)

    def _set(self, key: str, value) -> None:
        if self._settings is not None:
            if isinstance(value, bool):
                self._settings.set_boolean(key, value)
            elif isinstance(value, int):
                self._settings.set_int(key, value)
            elif isinstance(value, str):
                self._settings.set_string(key, value)
            else:
                raise TypeError(f"unsupported setting type: {type(value)!r}")
            self._settings.sync()
        else:
            self._fallback[key] = value

    @property
    def active_pool_id(self) -> str:
        return str(self._get("active-pool", "us-technician-2026"))

    def set_active_pool_id(self, pack_id: str) -> None:
        self._set("active-pool", pack_id)

    @property
    def mastery(self) -> MasteryConfig:
        return MasteryConfig(
            min_attempts=int(self._get("mastery-min-attempts", 3)),
            target_accuracy=int(self._get("mastery-accuracy", 80)) / 100.0,
            missed_gap=int(self._get("missed-gap", 5)),
        )

    def set_mastery(self, *, min_attempts: int, accuracy: int, missed_gap: int) -> None:
        self._set("mastery-min-attempts", int(min_attempts))
        self._set("mastery-accuracy", int(accuracy))
        self._set("missed-gap", int(missed_gap))

    @property
    def show_references(self) -> bool:
        return bool(self._get("show-references", True))

    def set_show_references(self, value: bool) -> None:
        self._set("show-references", bool(value))

    @property
    def timed_minutes(self) -> int:
        return int(self._get("timed-minutes", 30))

    def set_timed_minutes(self, value: int) -> None:
        self._set("timed-minutes", int(value))

    @property
    def window_size(self) -> tuple[int, int]:
        return (
            int(self._get("window-width", 960)),
            int(self._get("window-height", 720)),
        )

    def set_window_size(self, width: int, height: int) -> None:
        self._set("window-width", int(width))
        self._set("window-height", int(height))
