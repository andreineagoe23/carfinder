"""Shared pieces for per-site search link builders and fetchers."""

from __future__ import annotations

import re
import time
import unicodedata
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import ClassVar

import httpx

from carfinder.cache import Cache
from carfinder.models import Listing, Range, SearchLink, SearchProfile

# Seconds to wait between result pages of the same site; keeps us a polite, human-paced client.
PAGE_DELAY_S = 2.0


def slugify(text: str, sep: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", sep, ascii_text.lower()).strip(sep)


def snap_radius(km: int, allowed: Sequence[int]) -> tuple[int, str | None]:
    """Round up to the nearest radius the site offers, so no matching car is missed."""
    for radius in allowed:
        if radius >= km:
            note = None if radius == km else f"radius {km} km not offered, using {radius} km"
            return radius, note
    top = allowed[-1]
    return top, f"radius {km} km exceeds site maximum, using {top} km"


def span(r: Range, sep: str) -> str | None:
    """Render a range as "min<sep>max" with open ends left empty, or None if unbounded."""
    if r.min is None and r.max is None:
        return None
    return f"{'' if r.min is None else r.min}{sep}{'' if r.max is None else r.max}"


def parse_int(text: str | None) -> int | None:
    """German-formatted number to int: "132.000 km" -> 132000."""
    if not text:
        return None
    digits = re.sub(r"[^\d]", "", text)
    return int(digits) if digits else None


class Site(ABC):
    key: ClassVar[str]
    name: ClassVar[str]
    country: ClassVar[str] = "DE"
    can_fetch: ClassVar[bool] = False

    def __init__(self, client: httpx.Client, cache: Cache) -> None:
        self.client = client
        self.cache = cache

    def link(self, profile: SearchProfile) -> SearchLink:
        ids = self.resolve(profile, profile.overrides.get(self.key, {}))
        url, notes = self.build_url(profile, ids)
        return SearchLink(site=self.key, name=self.name, url=url, notes=notes)

    def resolve(self, profile: SearchProfile, overrides: dict[str, str]) -> dict[str, str]:
        """Look up site-specific identifiers (IDs, slugs). Overrides win over lookups."""
        return dict(overrides)

    @abstractmethod
    def build_url(self, profile: SearchProfile, ids: dict[str, str]) -> tuple[str, list[str]]:
        """Return the search URL plus notes on anything the site couldn't filter exactly."""

    def fetch(self, profile: SearchProfile, max_pages: int) -> list[Listing]:
        """Fetch result pages and return listings that really match the profile."""
        ids = self.resolve(profile, profile.overrides.get(self.key, {}))
        url = self.fetch_url(profile, ids)
        listings: list[Listing] = []
        for page in range(1, max_pages + 1):
            if page > 1:
                time.sleep(PAGE_DELAY_S)
            html = self.client.get(self.page_url(url, page)).raise_for_status().text
            found, has_more = self.parse_page(html, profile)
            listings += found
            if not has_more:
                break
        return [item for item in listings if matches(profile, item)]

    def fetch_url(self, profile: SearchProfile, ids: dict[str, str]) -> str:
        """URL the fetcher reads; differs from the link when robots.txt rules out some filters."""
        return self.build_url(profile, ids)[0]

    def page_url(self, url: str, page: int) -> str:
        raise NotImplementedError

    def parse_page(self, html: str, profile: SearchProfile) -> tuple[list[Listing], bool]:
        """Return the listings on one result page and whether a next page exists."""
        raise NotImplementedError


def matches(profile: SearchProfile, listing: Listing) -> bool:
    """Drop ads the site slipped in that don't fit the search (sponsored, wider area, ...)."""
    return (
        profile.price_eur.contains(listing.price_eur)
        and profile.mileage_km.contains(listing.mileage_km)
        and profile.year.contains(listing.year)
        and (not profile.fuel or listing.fuel is None or listing.fuel in profile.fuel)
        and (not profile.gearbox or listing.gearbox is None or listing.gearbox in profile.gearbox)
    )
