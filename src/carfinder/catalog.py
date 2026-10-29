"""Build the make/model catalog the web UI uses for its dropdowns.

mobile.de's lookup service is the most complete list and also gives the numeric IDs its
search URLs need. Browsers can't call it directly (no CORS), so we bake it into a JSON file.
"""

from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path

import httpx

from carfinder.sites.base import slugify
from carfinder.sites.mobile_de import LOOKUP_API


def build_catalog(client: httpx.Client, delay_s: float = 1.0) -> dict:
    makes = client.get(f"{LOOKUP_API}/makes/Car").raise_for_status().json()["makes"]
    catalog = []
    for make in sorted(makes, key=lambda m: m["n"].lower()):
        time.sleep(delay_s)
        models = client.get(f"{LOOKUP_API}/models/{make['i']}").raise_for_status().json()["models"]
        models = [m for m in models if m["n"].lower() not in ("andere", "others")]
        if not models:
            continue
        catalog.append(
            {
                "name": make["n"],
                "mobile_de": make["i"],
                "models": [{"name": m["n"], "mobile_de": m["i"]} for m in models],
            }
        )
    return {"generated": date.today().isoformat(), "makes": catalog}


DEFAULT_PATH = Path(__file__).resolve().parents[2] / "site" / "data" / "catalog.json"


def model_names(make: str, path: Path = DEFAULT_PATH) -> list[str]:
    """Model names for a make from the baked catalog (empty if the file isn't there)."""
    if not path.exists():
        return []
    wanted = compact(make)
    for entry in json.loads(path.read_text(encoding="utf-8"))["makes"]:
        if compact(entry["name"]) == wanted:
            return [m["name"] for m in entry["models"]]
    return []


def compact(text: str) -> str:
    """Lowercase letters and digits only: "CX-3" and "cx3" both become "cx3"."""
    return slugify(text, "-").replace("-", "")


# Short names sellers use for a make in ad titles.
MAKE_ALIASES = {"volkswagen": ["vw"], "mercedes benz": ["mercedes", "mb"], "alfa romeo": ["alfa"]}


def guess_model(title: str, make: str, models: list[str]) -> str | None:
    """Model named right after the make in an ad title, e.g. "Mazda CX3 2.0" -> "CX-3"."""
    words = slugify(title, " ").split()
    make_key = slugify(make, " ")
    tokens = None
    for variant in [make_key, *MAKE_ALIASES.get(make_key, [])]:
        n = len(variant.split())
        for i in range(len(words) - n + 1):
            if words[i : i + n] == variant.split():
                tokens = words[i + n : i + n + 3]
                break
        if tokens is not None:
            break
    if not tokens:
        return None
    # Longest first, so "CX-30" wins over "CX-3" and "323" over "3".
    for model in sorted(models, key=lambda m: len(compact(m)), reverse=True):
        key = compact(model)
        for k in range(1, len(tokens) + 1):
            joined = "".join(tokens[:k])
            # "cx3exclusive" is CX-3, but "30" is not "3": a digit can't run on.
            if joined == key or (joined.startswith(key) and not joined[len(key)].isdigit()):
                return model
    return None
