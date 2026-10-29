"""Tiny JSON cache for site lookups (make/model IDs, location IDs) that rarely change."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path


def default_path() -> Path:
    env = os.environ.get("CARFINDER_CACHE")
    return Path(env) if env else Path.home() / ".cache" / "carfinder" / "lookups.json"


class Cache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, str] = json.loads(path.read_text()) if path.exists() else {}

    def get_or_fetch(self, key: str, fetch: Callable[[], str]) -> str:
        if key not in self._data:
            self._data[key] = fetch()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True))
        return self._data[key]
