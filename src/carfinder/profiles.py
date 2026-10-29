"""Load search profiles from YAML files."""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from carfinder.models import SearchProfile


def default_dir() -> Path:
    return Path(os.environ.get("CARFINDER_PROFILES", "profiles"))


def list_profiles(directory: Path) -> list[str]:
    return sorted(p.stem for p in directory.glob("*.yaml"))


def load_profile(directory: Path, name: str) -> SearchProfile:
    path = directory / f"{name}.yaml"
    if not path.exists():
        known = ", ".join(list_profiles(directory)) or "none"
        raise FileNotFoundError(f"No profile '{name}' in {directory} (available: {known})")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return SearchProfile.model_validate(data)
