"""Romanian sites we only link to: they block automated reading or their filters are unreliable."""

from __future__ import annotations

from urllib.parse import quote, urlencode

from carfinder.models import Fuel, Gearbox, SearchProfile
from carfinder.sites.base import Site, slugify


class Olx(Site):
    """OLX.ro — big classifieds site, many private sellers. Blocks bots (403)."""

    key = "olx_ro"
    name = "OLX.ro"
    country = "RO"

    def build_url(self, profile: SearchProfile, ids: dict[str, str]) -> tuple[str, list[str]]:
        path = f"https://www.olx.ro/auto-masini-moto-ambarcatiuni/autoturisme/{slugify(profile.make, '-')}/"
        params: list[tuple[str, str]] = []
        if profile.model:
            params.append(("search[filter_enum_model][0]", slugify(profile.model, "-")))
        for name, r in (("year", profile.year), ("price", profile.price_eur)):
            if r.min is not None:
                params.append((f"search[filter_float_{name}:from]", str(r.min)))
            if r.max is not None:
                params.append((f"search[filter_float_{name}:to]", str(r.max)))
        notes = []
        if profile.fuel or profile.gearbox or profile.mileage_km.max is not None:
            notes.append("set fuel, gearbox and km on the site")
        if profile.ro_location.city:
            notes.append("pick the city on the site")
        return f"{path}?{urlencode(params)}" if params else path, notes


PUBLI24_FUELS = {Fuel.PETROL: "benzina", Fuel.DIESEL: "diesel"}


class Publi24(Site):
    """Publi24.ro — classifieds; only make/model/fuel/automatic filter reliably via URL."""

    key = "publi24"
    name = "Publi24"
    country = "RO"

    def build_url(self, profile: SearchProfile, ids: dict[str, str]) -> tuple[str, list[str]]:
        parts = ["https://www.publi24.ro/anunturi/auto-moto/masini-second-hand", slugify(profile.make, "-")]
        if profile.model:
            parts.append(slugify(profile.model, "-"))
        params: list[tuple[str, str]] = []
        if len(profile.fuel) == 1 and profile.fuel[0] in PUBLI24_FUELS:
            params.append(("carfueltype", PUBLI24_FUELS[profile.fuel[0]]))
        if profile.gearbox == [Gearbox.AUTOMATIC]:
            params.append(("gearname", "automata"))
        url = "/".join(parts) + "/"
        notes = ["set years, price and km on the site"]
        if profile.ro_location.city:
            notes.append("pick the city on the site")
        return (f"{url}?{urlencode(params)}" if params else url), notes


class AutoUncleRo(Site):
    """AutoUncle.ro — aggregator (Autovit, Publi24, …) with its own price rating."""

    key = "autouncle_ro"
    name = "AutoUncle.ro"
    country = "RO"

    def build_url(self, profile: SearchProfile, ids: dict[str, str]) -> tuple[str, list[str]]:
        parts = ["https://www.autouncle.ro/ro/masini-second-hand", quote(profile.make.replace(" ", "-"))]
        if profile.model:
            parts.append(quote(profile.model.replace(" ", "-")))
        notes = ["set years, price and km on the site"]
        if profile.ro_location.city:
            notes.append("pick the city on the site")
        return "/".join(parts), notes
