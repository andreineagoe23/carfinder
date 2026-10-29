"""Autovit.ro — Romania's largest car marketplace (OLX group), mostly dealers.

Result pages embed a GraphQL cache (urqlState) inside <script id="__NEXT_DATA__">.
robots.txt disallows URLs containing "_price", so the fetcher leaves the price filter
out and applies it locally; the link you open in the browser keeps it.
"""

from __future__ import annotations

import json
import re
from datetime import date
from urllib.parse import urlencode

from carfinder.models import Fuel, Gearbox, Listing, SearchProfile
from carfinder.sites.base import Site, slugify

SEARCH_URL = "https://www.autovit.ro/autoturisme"
RATES_API = "https://api.frankfurter.dev/v1/latest"
FUELS = {
    Fuel.PETROL: ["petrol"],
    Fuel.DIESEL: ["diesel"],
    Fuel.HYBRID: ["hybrid", "plugin-hybrid"],
    Fuel.ELECTRIC: ["electric"],
    Fuel.LPG: ["petrol-lpg"],
}
FUEL_VALUES = {value: fuel for fuel, values in FUELS.items() for value in values}
GEARBOXES = {Gearbox.MANUAL: "manual", Gearbox.AUTOMATIC: "automatic"}
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


class Autovit(Site):
    key = "autovit"
    name = "Autovit"
    country = "RO"
    can_fetch = True

    def resolve(self, profile: SearchProfile, overrides: dict[str, str]) -> dict[str, str]:
        return {
            "make_slug": overrides.get("make_slug") or slugify(profile.make, "-"),
            "model_slug": overrides.get("model_slug") or (slugify(profile.model, "-") if profile.model else ""),
        }

    def build_url(self, profile: SearchProfile, ids: dict[str, str]) -> tuple[str, list[str]]:
        return self._url(profile, ids, with_price=True), []

    def fetch_url(self, profile: SearchProfile, ids: dict[str, str]) -> str:
        return self._url(profile, ids, with_price=False)

    def _url(self, profile: SearchProfile, ids: dict[str, str], with_price: bool) -> str:
        path = "/".join(p for p in (SEARCH_URL, ids["make_slug"], ids["model_slug"]) if p)
        params: list[tuple[str, str]] = []
        ranges = [("year", profile.year), ("mileage", profile.mileage_km)]
        if with_price:
            ranges.append(("price", profile.price_eur))
        for name, r in ranges:
            if r.min is not None:
                params.append((f"search[filter_float_{name}:from]", str(r.min)))
            if r.max is not None:
                params.append((f"search[filter_float_{name}:to]", str(r.max)))
        fuels = [value for f in profile.fuel for value in FUELS[f]]
        params += [(f"search[filter_enum_fuel_type][{i}]", v) for i, v in enumerate(fuels)]
        if len(profile.gearbox) == 1:
            params.append(("search[filter_enum_gearbox]", GEARBOXES[profile.gearbox[0]]))
        return f"{path}?{urlencode(params)}" if params else path

    def page_url(self, url: str, page: int) -> str:
        if page == 1:
            return url
        return f"{url}{'&' if '?' in url else '?'}page={page}"

    def parse_page(self, html: str, profile: SearchProfile) -> tuple[list[Listing], bool]:
        match = NEXT_DATA.search(html)
        if not match:
            raise LookupError("Autovit page layout changed (no __NEXT_DATA__)")
        state = json.loads(match.group(1))["props"]["pageProps"].get("urqlState") or {}
        search = None
        for entry in state.values():
            data = entry.get("data")
            data = json.loads(data) if isinstance(data, str) else data
            if data and "advertSearch" in data:
                search = data["advertSearch"]
                break
        if search is None:
            raise LookupError("Autovit page layout changed (no advertSearch)")

        gearbox = profile.gearbox[0] if len(profile.gearbox) == 1 else None
        listings = [self.parse_node(edge["node"], gearbox) for edge in search.get("edges") or []]
        pager = search.get("pageInfo") or {}
        seen = int(pager.get("currentOffset") or 0) + int(pager.get("pageSize") or 0)
        return [x for x in listings if x], seen < int(search.get("totalCount") or 0)

    def parse_node(self, node: dict, gearbox: Gearbox | None) -> Listing | None:
        params = {p["key"]: p for p in node.get("parameters") or []}
        value = lambda key: (params.get(key) or {}).get("value")  # noqa: E731
        money = ((node.get("price") or {}).get("amount")) or {}
        amount, currency = money.get("units"), money.get("currencyCode") or "EUR"
        if not amount:
            return None
        location = node.get("location") or {}
        city = (location.get("city") or {}).get("name")
        region = (location.get("region") or {}).get("name")
        seller = node.get("seller") or {}
        seller_type = {"ProfessionalSeller": "dealer", "PrivateSeller": "private"}.get(seller.get("__typename"))
        thumbnail = node.get("thumbnail") or {}

        return Listing(
            source=self.key,
            source_id=str(node["id"]),
            country=self.country,
            url=node["url"],
            title=node.get("title") or "",
            model=(params.get("model") or {}).get("displayValue"),
            price_eur=self.to_eur(amount, currency),
            listed_price=amount if currency != "EUR" else None,
            listed_currency=currency if currency != "EUR" else None,
            mileage_km=int(value("mileage")) if value("mileage") else None,
            year=int(value("year")) if value("year") else None,
            fuel=FUEL_VALUES.get(value("fuel_type") or ""),
            gearbox=gearbox,
            power_hp=int(value("engine_power")) if value("engine_power") else None,  # CP ≈ hp
            city=", ".join(dict.fromkeys(p for p in (city, region) if p)) or None,
            seller_type=seller_type,
            seller_name=seller.get("name"),
            images=[img for img in (thumbnail.get("x2") or thumbnail.get("x1"),) if img],
        )

    def to_eur(self, amount: int, currency: str) -> int:
        if currency == "EUR":
            return int(amount)
        rate = self.cache.get_or_fetch(
            f"rate:{currency}:EUR:{date.today().isoformat()}",
            lambda: str(
                self.client.get(RATES_API, params={"base": currency, "symbols": "EUR"})
                .raise_for_status()
                .json()["rates"]["EUR"]
            ),
        )
        return round(amount * float(rate))
