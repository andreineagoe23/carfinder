"""Results on disk: one JSON file per search plus an index, read by the web UI.

results/
  index.json              [{id, name, summary, updated_at, count, new_count}, ...]
  searches/<id>.json      {id, query, updated_at, links, errors, listings: [...]}
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from carfinder.models import Listing, PricePoint, SearchLink, SearchProfile

ID_PATTERN = re.compile(r"^[a-f0-9]{12}$")


class SearchResult(BaseModel):
    id: str
    query: SearchProfile
    created_at: str
    updated_at: str
    requested_at: str | None = None  # last time someone started this search (not the scheduler)
    links: list[SearchLink] = []
    errors: dict[str, str] = {}
    listings: list[Listing] = []

    @property
    def new_listings(self) -> list[Listing]:
        return [x for x in self.listings if x.first_seen == self.updated_at]


class IndexEntry(BaseModel):
    id: str
    name: str
    summary: str
    updated_at: str
    count: int
    new_count: int


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def check_id(search_id: str) -> str:
    if not ID_PATTERN.match(search_id):
        raise ValueError(f"invalid search id {search_id!r}")
    return search_id


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.searches = root / "searches"

    def path(self, search_id: str) -> Path:
        return self.searches / f"{check_id(search_id)}.json"

    def load(self, search_id: str) -> SearchResult | None:
        path = self.path(search_id)
        return SearchResult.model_validate_json(path.read_text()) if path.exists() else None

    def all(self) -> list[SearchResult]:
        return [SearchResult.model_validate_json(p.read_text()) for p in sorted(self.searches.glob("*.json"))]

    def save(self, result: SearchResult) -> None:
        self.searches.mkdir(parents=True, exist_ok=True)
        self.path(result.id).write_text(result.model_dump_json(indent=1))
        self.write_index()

    def recently_requested(self, days: int, limit: int, now: datetime | None = None) -> list[SearchResult]:
        """Searches someone started in the last `days` days, newest first."""
        cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
        recent = [r for r in self.all() if parse_iso(r.requested_at or r.created_at) >= cutoff]
        return sorted(recent, key=lambda r: r.requested_at or r.created_at, reverse=True)[:limit]

    def prune(self, days: int, now: datetime | None = None) -> list[str]:
        """Delete searches nobody has started for `days` days; returns their IDs."""
        cutoff = (now or datetime.now(UTC)) - timedelta(days=days)
        stale = [r.id for r in self.all() if parse_iso(r.requested_at or r.created_at) < cutoff]
        for search_id in stale:
            self.path(search_id).unlink()
        if stale:
            self.write_index()
        return stale

    def delete(self, search_id: str) -> bool:
        path = self.path(search_id)
        if not path.exists():
            return False
        path.unlink()
        self.write_index()
        return True

    def write_index(self) -> None:
        entries = [
            IndexEntry(
                id=r.id,
                name=r.query.title,
                summary=r.query.summary(),
                updated_at=r.updated_at,
                count=len(r.listings),
                new_count=len(r.new_listings),
            ).model_dump()
            for r in sorted(self.all(), key=lambda r: r.updated_at, reverse=True)
        ]
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "index.json").write_text(json.dumps(entries, indent=1, ensure_ascii=False))


def merge_history(previous: SearchResult | None, listings: list[Listing], at: str) -> list[Listing]:
    """Carry first-seen dates and price history over from the last run."""
    before = {x.key: x for x in previous.listings} if previous else {}
    for listing in listings:
        old = before.get(listing.key)
        listing.last_seen = at
        if old is None:
            listing.first_seen = at
            listing.price_history = [PricePoint(at=at, price_eur=listing.price_eur)]
            continue
        listing.first_seen = old.first_seen or at
        listing.price_history = list(old.price_history)
        if not listing.price_history or listing.price_history[-1].price_eur != listing.price_eur:
            listing.price_history.append(PricePoint(at=at, price_eur=listing.price_eur))
    return listings
