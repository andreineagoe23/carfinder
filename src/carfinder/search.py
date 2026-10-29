"""One search run: build links, fetch every site that allows it, merge, score, save."""

from __future__ import annotations

import httpx

from carfinder.cache import Cache
from carfinder.catalog import guess_model, model_names
from carfinder.dedupe import dedupe
from carfinder.models import Listing, SearchProfile
from carfinder.scoring import score
from carfinder.sites import SITES, build_links
from carfinder.store import SearchResult, Store, check_id, merge_history, now_iso


def run_search(
    profile: SearchProfile,
    client: httpx.Client,
    cache: Cache,
    store: Store,
    search_id: str | None = None,
    max_pages: int = 3,
    at: str | None = None,
) -> SearchResult:
    search_id = check_id(search_id or profile.query_id())
    at = at or now_iso()
    links = build_links(profile, client, cache)
    errors = {link.site: link.error for link in links if link.error}

    fetched = []
    for link in links:
        site = SITES[link.site](client, cache)
        if link.error or not site.can_fetch:
            continue
        try:
            fetched += site.fetch(profile, max_pages)
        except (httpx.HTTPError, LookupError, ValueError, KeyError) as exc:
            errors[link.site] = f"fetch failed: {exc}"

    label_models(profile, fetched)
    previous = store.load(search_id)
    # A site that failed this time keeps its last known listings rather than having them vanish
    # (and reappear as "new" on the next successful run).
    carried = [
        x.model_copy(update={"also_on": [], "flags": []})
        for x in (previous.listings if previous else [])
        if x.source in errors
    ]
    listings = score(merge_history(previous, dedupe(fetched + carried), at))

    result = SearchResult(
        id=search_id,
        query=profile,
        created_at=previous.created_at if previous else at,
        updated_at=at,
        links=links,
        errors=errors,
        listings=listings,
    )
    store.save(result)
    return result


def label_models(profile: SearchProfile, listings: list[Listing]) -> None:
    """Make sure every listing knows its model, so prices are compared like for like."""
    known = model_names(profile.make) if not profile.model else []
    for listing in listings:
        if listing.model is None:
            listing.model = profile.model or guess_model(listing.title, profile.make, known)
