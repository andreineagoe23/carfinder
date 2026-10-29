"""AutoScout24 — large EU-wide marketplace. Uses make/model slugs in the URL path.

Result pages embed their data as JSON in a <script id="__NEXT_DATA__"> tag.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlencode

from carfinder.models import Fuel, Gearbox, Listing, SearchProfile
from carfinder.sites.base import Site, parse_int, slugify, snap_radius

BASE_URL = "https://www.autoscout24.de"
SEARCH_URL = f"{BASE_URL}/lst"
RADII = (10, 20, 50, 100, 150, 200)
FUELS = {
    Fuel.PETROL: "B",
    Fuel.DIESEL: "D",
    Fuel.HYBRID: "2",  # electric/petrol
    Fuel.ELECTRIC: "E",
    Fuel.LPG: "L",
}
FUEL_CODES = {code.lower(): fuel for fuel, code in FUELS.items()} | {"3": Fuel.HYBRID}
GEARBOXES = {Gearbox.MANUAL: "M", Gearbox.AUTOMATIC: "A"}
GEARBOX_NAMES = {"schaltgetriebe": Gearbox.MANUAL, "automatik": Gearbox.AUTOMATIC, "halbautomatik": Gearbox.AUTOMATIC}
COUNTRIES = {"DE": "D", "AT": "A", "NL": "NL", "BE": "B", "LU": "L", "FR": "F", "IT": "I", "ES": "E"}
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


class AutoScout24(Site):
    key = "autoscout24"
    name = "AutoScout24"
    can_fetch = True

    def resolve(self, profile: SearchProfile, overrides: dict[str, str]) -> dict[str, str]:
        return {
            "make_slug": overrides.get("make_slug") or slugify(profile.make, "-"),
            "model_slug": overrides.get("model_slug") or slugify(profile.model, "-"),
        }

    def build_url(self, profile: SearchProfile, ids: dict[str, str]) -> tuple[str, list[str]]:
        country = profile.location.country.upper()
        if country not in COUNTRIES:
            raise LookupError(f"AutoScout24 country '{country}' not supported")
        notes: list[str] = []
        radius, note = snap_radius(profile.location.radius_km, RADII)
        if note:
            notes.append(note)

        params: list[tuple[str, str]] = [
            ("atype", "C"),
            ("cy", COUNTRIES[country]),
            ("damaged_listing", "exclude"),
            ("ustate", "N,U"),
            ("sort", "standard"),
            ("desc", "0"),
        ]
        for key, value in (
            ("fregfrom", profile.year.min),
            ("fregto", profile.year.max),
            ("kmfrom", profile.mileage_km.min),
            ("kmto", profile.mileage_km.max),
            ("pricefrom", profile.price_eur.min),
            ("priceto", profile.price_eur.max),
        ):
            if value is not None:
                params.append((key, str(value)))
        if profile.fuel:
            params.append(("fuel", ",".join(FUELS[f] for f in profile.fuel)))
        if profile.gearbox:
            params.append(("gear", ",".join(GEARBOXES[g] for g in profile.gearbox)))
        params += [("zip", profile.location.zip), ("zipr", str(radius))]

        path = f"{SEARCH_URL}/{ids['make_slug']}/{ids['model_slug']}"
        return f"{path}?{urlencode(params)}", notes

    def page_url(self, url: str, page: int) -> str:
        return f"{url}&page={page}"

    def parse_page(self, html: str, profile: SearchProfile) -> tuple[list[Listing], bool]:
        match = NEXT_DATA.search(html)
        if not match:
            raise LookupError("AutoScout24 page layout changed (no __NEXT_DATA__)")
        props = json.loads(match.group(1))["props"]["pageProps"]
        listings = [parse_listing(raw) for raw in props.get("listings") or []]
        page = int((props.get("pageQuery") or {}).get("page", 1))
        return listings, page < int(props.get("numberOfPages") or 1)


def parse_listing(raw: dict) -> Listing:
    vehicle = raw.get("vehicle") or {}
    tracking = raw.get("tracking") or {}
    location = raw.get("location") or {}
    seller = raw.get("seller") or {}
    details = {d.get("iconName"): d.get("data") for d in raw.get("vehicleDetails") or []}

    reg = tracking.get("firstRegistration") or ""  # "04-2016"
    year = int(reg[-4:]) if re.fullmatch(r"\d{2}-\d{4}", reg) else None
    power = re.search(r"\((\d+) PS\)", details.get("speedometer") or "")
    gearbox_name = (vehicle.get("transmission") or "").lower()
    label = tracking.get("priceLabel")
    title = " ".join(
        p for p in (vehicle.get("make"), vehicle.get("model"), vehicle.get("modelVersionInput")) if p
    )

    return Listing(
        source="autoscout24",
        source_id=str(raw["id"]),
        url=BASE_URL + raw["url"],
        title=title or raw.get("title") or "",
        price_eur=(raw.get("price") or {}).get("priceRaw") or parse_int(tracking.get("price")) or 0,
        price_label=label if label and label != "unknown" else None,
        mileage_km=parse_int(tracking.get("mileage")),
        year=year,
        first_registration=reg.replace("-", "/") if year else None,
        fuel=FUEL_CODES.get((tracking.get("fuelType") or "").lower()),
        gearbox=GEARBOX_NAMES.get(gearbox_name),
        power_hp=int(power.group(1)) if power else None,
        zip=location.get("zip"),
        city=location.get("city"),
        distance_km=location.get("distanceToSearchLocationInKm"),
        seller_type={"Dealer": "dealer", "PrivateSeller": "private"}.get(seller.get("type")),
        seller_name=seller.get("companyName"),
        images=[img.replace("/250x188.webp", "/480x360.webp") for img in (raw.get("images") or [])[:6]],
    )
