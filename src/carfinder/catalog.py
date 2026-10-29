"""Build the make/model catalog the web UI uses for its dropdowns.

mobile.de's lookup service is the most complete list and also gives the numeric IDs its
search URLs need. Browsers can't call it directly (no CORS), so we bake it into a JSON file.
"""

from __future__ import annotations

import time
from datetime import date

import httpx

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
