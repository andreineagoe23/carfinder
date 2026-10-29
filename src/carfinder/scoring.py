"""Rank listings 0–100 and flag things worth a second look.

The "market" is the result set itself: each car is compared with cars of a similar age
found in the same search. Rough, but it needs no outside price data.
"""

from __future__ import annotations

import re
from datetime import date
from statistics import median

from carfinder.catalog import compact
from carfinder.models import Listing

PRICE_LABEL_POINTS = {
    "top-price": 15,
    "good-price": 10,
    "fair-price": 5,
    "somewhat-expensive": 0,
    "expensive": -5,
}
MIN_COMPARABLES = 3
# German words in ad titles that mean damage, defects or "for export / tinkerers".
DAMAGE_WORDS = re.compile(
    r"unfall|schaden|defekt|bastler|export|ohne tüv|motorproblem|getriebeproblem|reparatur",
    re.IGNORECASE,
)


def market_price(listing: Listing, all_listings: list[Listing]) -> float | None:
    """Median price of other cars of the same model within a year of this one."""
    if listing.year is None or listing.model is None:
        return None
    comparables = [
        other.price_eur
        for other in all_listings
        if other is not listing
        and other.year is not None
        and abs(other.year - listing.year) <= 1
        and other.model is not None
        and compact(other.model) == compact(listing.model)
    ]
    return median(comparables) if len(comparables) >= MIN_COMPARABLES else None


def km_per_year(listing: Listing, today: date) -> float | None:
    if listing.mileage_km is None or listing.year is None:
        return None
    age = max(today.year - listing.year, 1)
    return listing.mileage_km / age


def score(listings: list[Listing], today: date | None = None) -> list[Listing]:
    today = today or date.today()
    for listing in listings:
        points = 40.0
        parts: list[str] = []
        flags = list(listing.flags)

        def add(delta: float, reason: str) -> None:
            nonlocal points
            points += delta
            if round(delta):
                parts.append(f"{reason} ({round(delta):+d})")

        market = market_price(listing, listings)
        if market:
            gap = (market - listing.price_eur) / market  # +0.2 = 20 % below market
            diff = abs(market - listing.price_eur)
            where = "below" if gap >= 0 else "above"
            add(max(-20, min(25, gap * 100)), f"€{diff:,.0f} {where} similar {listing.model} cars (median €{market:,.0f})")
            if gap >= 0.30:
                flags.append(f"{gap:.0%} below similar cars — check for damage or scam")
        else:
            parts.append("Too few similar cars in this search to compare the price")

        per_year = km_per_year(listing, today)
        if per_year is not None:
            add(max(-10, min(15, (20_000 - per_year) / 1000)), f"~{per_year:,.0f} km per year")
            if per_year > 25_000:
                flags.append(f"High mileage: ~{per_year:,.0f} km/year")

        if listing.price_label in PRICE_LABEL_POINTS:
            add(PRICE_LABEL_POINTS[listing.price_label], f"Site rates it “{listing.price_label.replace('-', ' ')}”")
        if listing.seller_type == "dealer":
            add(5, "Dealer: 12 months' warranty in Germany" if listing.country == "DE" else "Dealer")
        elif listing.seller_type == "private":
            flags.append("Private seller: usually sold without warranty")
        if damage := DAMAGE_WORDS.search(listing.title):
            add(-20, f"Title mentions “{damage.group(0)}”")
            flags.append(f"Title mentions “{damage.group(0)}” — likely damage or defect")
        if not listing.images:
            add(-10, "No photos")
            flags.append("No photos")
        if listing.old_price_eur:
            flags.append(f"Price reduced from €{listing.old_price_eur:,}")
        if len(listing.price_history) > 1 and listing.price_history[-1].price_eur < listing.price_history[0].price_eur:
            flags.append(f"Price dropped since first seen (€{listing.price_history[0].price_eur:,})")

        listing.score = round(max(0, min(100, points)))
        listing.score_parts = parts
        listing.flags = list(dict.fromkeys(flags))
    return sorted(listings, key=lambda x: x.score or 0, reverse=True)
