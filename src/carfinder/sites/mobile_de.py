"""mobile.de — Germany's largest car marketplace. Uses numeric make/model IDs.

Location is given as coordinates: ll=<lat>,<lng>&rd=<radius km>&gn=<place name>
(the older zip/zipr parameters are ignored by the site).
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from carfinder.models import Fuel, Gearbox, SearchProfile
from carfinder.sites.base import Site, slugify, snap_radius, span

LOOKUP_API = "https://m.mobile.de/svc/r"
GEOCODE_API = "https://api.zippopotam.us"  # postcode -> coordinates, free and keyless
SEARCH_URL = "https://suchen.mobile.de/fahrzeuge/search.html"
RADII = (10, 20, 50, 100, 150, 200)
FUELS = {
    Fuel.PETROL: "PETROL",
    Fuel.DIESEL: "DIESEL",
    Fuel.HYBRID: "HYBRID",
    Fuel.ELECTRIC: "ELECTRICITY",
    Fuel.LPG: "LPG",
}
GEARBOXES = {Gearbox.MANUAL: "MANUAL_GEAR", Gearbox.AUTOMATIC: "AUTOMATIC_GEAR"}


class MobileDe(Site):
    key = "mobile_de"
    name = "mobile.de"

    def resolve(self, profile: SearchProfile, overrides: dict[str, str]) -> dict[str, str]:
        make_id = overrides.get("make_id") or self.cache.get_or_fetch(
            f"mobile_de:make:{slugify(profile.make, '-')}",
            lambda: self._find_id(f"{LOOKUP_API}/makes/Car", "makes", profile.make),
        )
        model_id = ""
        if profile.model:
            model_id = overrides.get("model_id") or self.cache.get_or_fetch(
                f"mobile_de:model:{make_id}:{slugify(profile.model, '-')}",
                lambda: self._find_id(f"{LOOKUP_API}/models/{make_id}", "models", profile.model),
            )
        return {"make_id": make_id, "model_id": model_id, **self._place(profile)}

    def _place(self, profile: SearchProfile) -> dict[str, str]:
        """Coordinates and name of the search zip, or nothing if the lookup fails."""
        country, zip_code = profile.location.country.lower(), profile.location.zip
        try:
            found = self.cache.get_or_fetch(
                f"geo:{country}:{zip_code}", lambda: self._geocode(country, zip_code)
            )
        except (httpx.HTTPError, LookupError):
            return {}
        lat_lng, name = found.split("|", 1)
        return {"lat_lng": lat_lng, "place": name}

    def _geocode(self, country: str, zip_code: str) -> str:
        data = self.client.get(f"{GEOCODE_API}/{country}/{zip_code}").raise_for_status().json()
        place = (data.get("places") or [None])[0]
        if not place:
            raise LookupError(f"unknown zip {zip_code}")
        name = ", ".join(p for p in (place.get("place name"), place.get("state")) if p)
        return f"{place['latitude']},{place['longitude']}|{name}"

    def _find_id(self, url: str, kind: str, wanted: str) -> str:
        items = self.client.get(url).raise_for_status().json()[kind]
        for item in items:
            if slugify(item["n"], "-") == slugify(wanted, "-"):
                return str(item["i"])
        sample = ", ".join(item["n"] for item in items[:40])
        raise LookupError(f"mobile.de has no {kind[:-1]} named '{wanted}'. Known: {sample}")

    def build_url(self, profile: SearchProfile, ids: dict[str, str]) -> tuple[str, list[str]]:
        notes: list[str] = []
        radius, note = snap_radius(profile.location.radius_km, RADII)
        if note:
            notes.append(note)

        params: list[tuple[str, str]] = [
            ("isSearchRequest", "true"),
            ("s", "Car"),
            ("vc", "Car"),
            ("dam", "false"),  # exclude damaged cars
            ("ms", f"{ids['make_id']};{ids['model_id']};;"),
        ]
        for key, value in (
            ("fr", span(profile.year, ":")),
            ("ml", span(profile.mileage_km, ":")),
            ("p", span(profile.price_eur, ":")),
        ):
            if value:
                params.append((key, value))
        params += [("ft", FUELS[f]) for f in profile.fuel]
        params += [("tr", GEARBOXES[g]) for g in profile.gearbox]
        params.append(("cn", profile.location.country))
        if ids.get("lat_lng"):
            params += [("ll", ids["lat_lng"]), ("rd", str(radius)), ("gn", ids["place"])]
        else:
            notes.append(f"couldn't locate zip {profile.location.zip}; set the location on the site")
        return f"{SEARCH_URL}?{urlencode(params)}", notes
