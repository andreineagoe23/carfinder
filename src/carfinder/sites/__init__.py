"""Registry of supported marketplaces. Add a site: subclass Site, list it in SITES."""

from __future__ import annotations

import httpx

from carfinder.cache import Cache
from carfinder.models import SearchLink, SearchProfile
from carfinder.sites.autoscout24 import AutoScout24
from carfinder.sites.base import Site
from carfinder.sites.kleinanzeigen import Kleinanzeigen
from carfinder.sites.mobile_de import MobileDe

SITES: dict[str, type[Site]] = {s.key: s for s in (MobileDe, AutoScout24, Kleinanzeigen)}


def build_links(
    profile: SearchProfile,
    client: httpx.Client,
    cache: Cache,
    only: list[str] | None = None,
) -> list[SearchLink]:
    keys = only or profile.sites or list(SITES)
    unknown = [k for k in keys if k not in SITES]
    if unknown:
        raise ValueError(f"Unknown site(s): {', '.join(unknown)}. Known: {', '.join(SITES)}")

    links = []
    for key in keys:
        site = SITES[key](client, cache)
        try:
            links.append(site.link(profile))
        except (httpx.HTTPError, LookupError) as exc:
            links.append(SearchLink(site=key, name=site.name, error=str(exc)))
    return links
