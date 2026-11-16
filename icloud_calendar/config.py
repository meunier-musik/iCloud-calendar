"""Konfiguration und Pfade."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Optional

APP_NAME = "icloud-calendar"


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(base) / APP_NAME


def config_file() -> Path:
    return config_dir() / "config.json"


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache"))
    return Path(base) / APP_NAME


def db_file() -> Path:
    return cache_dir() / "calendar.db"


def style_file() -> Path:
    return Path(__file__).resolve().parent.parent / "style" / "app.css"


class Config:
    """App-Konfiguration (iCloud-Zugangsdaten etc.)."""

    def __init__(self):
        self.path = config_file()
        self.data: dict = {}
        self.load()

    def load(self) -> None:
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        try:
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
        except OSError:
            pass

    # ---------- Zugangsdaten ----------

    @property
    def username(self) -> str:
        return self.data.get("username", "")

    @property
    def password(self) -> str:
        return self.data.get("password", "")

    @property
    def account_configured(self) -> bool:
        return bool(self.username and self.password)

    def set_account(self, username: str, password: str) -> None:
        self.data["username"] = username
        self.data["password"] = password
        self.save()

    # ---------- Sonstiges ----------

    @property
    def view(self) -> str:
        return self.data.get("view", "month")

    def set_view(self, view: str) -> None:
        self.data["view"] = view
        self.save()

    @property
    def color_overrides(self) -> dict:
        return self.data.setdefault("colors", {})

    def set_calendar_color(self, uid: str, color: str) -> None:
        self.color_overrides[uid] = color
        self.save()


def get_config() -> Config:
    return Config()
