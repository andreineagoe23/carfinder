"""Merge the same car listed on several sites (dealers often post everywhere)."""

from __future__ import annotations

from carfinder.models import Listing, SearchLink
from carfinder.sites import SITES

# Site order of preference for the listing we keep: richer data first.
PREFERENCE = ["autoscout24", "kleinanzeigen"]


def same_car(a: Listing, b: Listing) -> bool:
    if a.source == b.source or None in (a.mileage_km, b.mileage_km, a.year, b.year):
        return False
    if a.first_registration and b.first_registration and a.first_registration != b.first_registration:
        return False
    # Sellers often price the same car differently per site, so price is only a loose check.
    return (
        a.year == b.year
        and abs(a.mileage_km - b.mileage_km) <= 500
        and abs(a.price_eur - b.price_eur) <= 0.15 * max(a.price_eur, b.price_eur)
        and (a.zip == b.zip or _town(a) == _town(b) != "")
    )


def _town(listing: Listing) -> str:
    return (listing.city or "").lower().split(" ")[0]


def dedupe(listings: list[Listing]) -> list[Listing]:
    # Sites repeat promoted ads across result pages: keep one per ad ID first.
    unique = list({x.key: x for x in reversed(listings)}.values())[::-1]
    ordered = sorted(unique, key=lambda x: PREFERENCE.index(x.source) if x.source in PREFERENCE else 99)
    kept: list[Listing] = []
    for listing in ordered:
        twin = next((k for k in kept if same_car(k, listing)), None)
        if twin is None:
            kept.append(listing)
            continue
        name = SITES[listing.source].name if listing.source in SITES else listing.source
        twin.also_on.append(SearchLink(site=listing.source, name=name, url=listing.url))
        if listing.price_eur < twin.price_eur:
            twin.flags.append(f"Cheaper on {name}: €{listing.price_eur:,}")
    return kept
