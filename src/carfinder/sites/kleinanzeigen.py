"""Kleinanzeigen (ex eBay Kleinanzeigen) — many private sellers; Germany only.

Filters live in the URL path, e.g.
/s-autos/93339/preis:8000:10000/c216l6234r200+autos.ez_i:2015%2C2017+autos.marke_s:mazda
Page N inserts a "seite:N" segment before the category segment.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from selectolax.lexbor import LexborHTMLParser

from carfinder.models import Fuel, Gearbox, Listing, SearchProfile
from carfinder.sites.base import Site, parse_int, slugify, snap_radius, span

BASE_URL = "https://www.kleinanzeigen.de"
CARS_CATEGORY = "c216"
RADII = (5, 10, 20, 30, 50, 100, 150, 200)
FUELS = {
    Fuel.PETROL: "benzin",
    Fuel.DIESEL: "diesel",
    Fuel.HYBRID: "hybrid",
    Fuel.ELECTRIC: "elektro",
    Fuel.LPG: "lpg",
}
GEARBOXES = {Gearbox.MANUAL: "manuell", Gearbox.AUTOMATIC: "automatik"}
PRICE = re.compile(r"([\d.]+)\s*€")
REGISTRATION = re.compile(r"EZ (\d{2})/(\d{4})")
MILEAGE = re.compile(r"^([\d.]+) km$")
PLACE = re.compile(r"^(\d{5})\s+(.+)$")


class Kleinanzeigen(Site):
    key = "kleinanzeigen"
    name = "Kleinanzeigen"
    can_fetch = True

    def resolve(self, profile: SearchProfile, overrides: dict[str, str]) -> dict[str, str]:
        if profile.location.country.upper() != "DE":
            raise LookupError("Kleinanzeigen only covers Germany")
        zip_code = profile.location.zip
        location_id = overrides.get("location_id") or self.cache.get_or_fetch(
            f"kleinanzeigen:location:{zip_code}", lambda: self._find_location(zip_code)
        )
        return {
            "make_slug": overrides.get("make_slug") or slugify(profile.make, "_"),
            "model_slug": overrides.get("model_slug") or (slugify(profile.model, "_") if profile.model else ""),
            "location_id": location_id,
        }

    def _find_location(self, zip_code: str) -> str:
        url = f"{BASE_URL}/s-ort-empfehlungen.json"
        suggestions = self.client.get(url, params={"query": zip_code}).raise_for_status().json()
        for key, label in suggestions.items():
            if key != "_0" and label.startswith(zip_code):
                return key.lstrip("_")
        raise LookupError(f"Kleinanzeigen doesn't know zip {zip_code}")

    def build_url(self, profile: SearchProfile, ids: dict[str, str]) -> tuple[str, list[str]]:
        notes: list[str] = []
        radius, note = snap_radius(profile.location.radius_km, RADII)
        if note:
            notes.append(note)

        filters: dict[str, str] = {"autos.marke_s": ids["make_slug"]}
        if ids["model_slug"]:
            filters["autos.model_s"] = ids["model_slug"]
        if years := span(profile.year, ","):
            filters["autos.ez_i"] = years
        if km := span(profile.mileage_km, ","):
            filters["autos.km_i"] = km
        # The site accepts only one fuel / gearbox value; with several, leave it unfiltered.
        if len(profile.fuel) == 1:
            filters["autos.fuel_s"] = FUELS[profile.fuel[0]]
        elif profile.fuel:
            notes.append("only one fuel type can be filtered; showing all fuels")
        if len(profile.gearbox) == 1:
            filters["autos.shift_s"] = GEARBOXES[profile.gearbox[0]]
        elif profile.gearbox:
            notes.append("only one gearbox can be filtered; showing all gearboxes")

        segments = [profile.location.zip]
        if price := span(profile.price_eur, ":"):
            segments.append(f"preis:{price}")
        filter_part = "".join(f"+{k}:{quote(v, safe='')}" for k, v in sorted(filters.items()))
        segments.append(f"{CARS_CATEGORY}l{ids['location_id']}r{radius}{filter_part}")
        return f"{BASE_URL}/s-autos/{'/'.join(segments)}", notes

    def page_url(self, url: str, page: int) -> str:
        if page == 1:
            return url
        head, last = url.rsplit("/", 1)
        return f"{head}/seite:{page}/{last}"

    def parse_page(self, html: str, profile: SearchProfile) -> tuple[list[Listing], bool]:
        tree = LexborHTMLParser(html)
        table = tree.css_first("#srchrslt-adtable")
        if table is None:
            return [], False
        # Without a fuel/gearbox column on the result card, a single-value filter tells us the value.
        fuel = profile.fuel[0] if len(profile.fuel) == 1 else None
        gearbox = profile.gearbox[0] if len(profile.gearbox) == 1 else None
        listings = [parse_article(node, fuel, gearbox) for node in table.css("article[data-adid]")]
        has_more = tree.css_first('a[title="Nächste"]') is not None
        return [item for item in listings if item], has_more


def parse_article(node, fuel: Fuel | None, gearbox: Gearbox | None) -> Listing | None:
    link = node.css_first("h3 a") or node.css_first("h2 a")
    texts = [t.strip() for t in node.text(separator="\n").split("\n") if t.strip()]
    prices = [parse_int(m.group(1)) for t in texts if (m := PRICE.fullmatch(t.replace(" VB", "")))]
    if link is None or not prices:
        return None

    mileage = next((parse_int(m.group(1)) for t in texts if (m := MILEAGE.match(t))), None)
    registration = next((m for t in texts if (m := REGISTRATION.search(t))), None)
    place = next((m for t in texts if (m := PLACE.match(t))), None)
    distance = next((parse_int(t) for t in texts if re.fullmatch(r"\(\d+ km\)", t)), None)
    image = node.css_first("img")
    href = node.attributes.get("data-href") or link.attributes.get("href") or ""

    return Listing(
        source="kleinanzeigen",
        source_id=node.attributes["data-adid"],
        url=BASE_URL + href,
        title=link.text(strip=True),
        price_eur=prices[0],
        old_price_eur=prices[1] if len(prices) > 1 and prices[1] > prices[0] else None,
        negotiable=any(t.endswith("VB") for t in texts),
        mileage_km=mileage,
        year=int(registration.group(2)) if registration else None,
        first_registration=f"{registration.group(1)}/{registration.group(2)}" if registration else None,
        fuel=fuel,
        gearbox=gearbox,
        zip=place.group(1) if place else None,
        city=place.group(2) if place else None,
        distance_km=distance,
        images=[image.attributes["src"].replace("rule=$_2.", "rule=$_59.")]
        if image is not None and image.attributes.get("src")
        else [],
    )
