from urllib.parse import parse_qsl, urlsplit

import pytest

from carfinder.sites import build_links
from carfinder.sites.autoscout24 import AutoScout24
from carfinder.sites.base import slugify, snap_radius
from carfinder.sites.kleinanzeigen import Kleinanzeigen
from carfinder.sites.mobile_de import MobileDe
from tests.conftest import fake_client

MOBILE_ROUTES = {
    "/svc/r/makes/Car": {"makes": [{"i": 3500, "n": "BMW"}, {"i": 16800, "n": "Mazda"}]},
    "/svc/r/models/16800": {"models": [{"i": 34, "n": "CX-3"}, {"i": 42, "n": "CX-30"}]},
}
KLEIN_ROUTES = {"/s-ort-empfehlungen.json": {"_0": "Deutschland", "_6234": "93339 Riedenburg"}}


def query(url: str) -> list[tuple[str, str]]:
    return parse_qsl(urlsplit(url).query)


def test_slugify():
    assert slugify("CX-3", "-") == "cx-3"
    assert slugify("Mercedes-Benz", "_") == "mercedes_benz"
    assert slugify("Škoda", "-") == "skoda"


def test_snap_radius_rounds_up():
    assert snap_radius(200, (50, 100, 200)) == (200, None)
    assert snap_radius(120, (50, 100, 200))[0] == 200
    assert snap_radius(300, (50, 100, 200))[0] == 200


def test_mobile_de_resolves_ids_and_builds_url(profile, cache):
    site = MobileDe(fake_client(MOBILE_ROUTES), cache)
    link = site.link(profile)
    q = query(link.url)
    assert ("ms", "16800;34;;") in q
    assert ("fr", "2015:2017") in q
    assert ("ml", ":160000") in q
    assert ("p", "8000:10000") in q
    assert ("ft", "PETROL") in q
    assert ("zip", "93339") in q and ("zipr", "200") in q
    assert link.notes == []


def test_mobile_de_caches_lookups(profile, cache):
    MobileDe(fake_client(MOBILE_ROUTES), cache).link(profile)
    offline = MobileDe(fake_client({}), cache)
    assert ("ms", "16800;34;;") in query(offline.link(profile).url)


def test_mobile_de_unknown_model(profile, cache):
    profile.model = "CX-99"
    with pytest.raises(LookupError, match="CX-99"):
        MobileDe(fake_client(MOBILE_ROUTES), cache).link(profile)


def test_autoscout24_url(profile, cache):
    profile.gearbox = ["manual", "automatic"]
    link = AutoScout24(fake_client({}), cache).link(profile)
    assert urlsplit(link.url).path == "/lst/mazda/cx-3"
    q = dict(query(link.url))
    assert q["fregfrom"] == "2015" and q["fregto"] == "2017"
    assert q["kmto"] == "160000" and "kmfrom" not in q
    assert q["pricefrom"] == "8000" and q["priceto"] == "10000"
    assert q["fuel"] == "B"
    assert q["gear"] == "M,A"
    assert q["cy"] == "D" and q["zip"] == "93339" and q["zipr"] == "200"


def test_kleinanzeigen_url(profile, cache):
    link = Kleinanzeigen(fake_client(KLEIN_ROUTES), cache).link(profile)
    assert link.url == (
        "https://www.kleinanzeigen.de/s-autos/93339/preis:8000:10000/c216l6234r200"
        "+autos.ez_i:2015%2C2017+autos.fuel_s:benzin+autos.km_i:%2C160000"
        "+autos.marke_s:mazda+autos.model_s:cx_3"
    )


def test_kleinanzeigen_multiple_fuels_unfiltered(profile, cache):
    profile.fuel = ["petrol", "hybrid"]
    link = Kleinanzeigen(fake_client(KLEIN_ROUTES), cache).link(profile)
    assert "fuel_s" not in link.url
    assert any("fuel" in n for n in link.notes)


def test_build_links_reports_site_errors_without_failing_others(profile, cache):
    links = build_links(profile, fake_client({}), cache)
    by_site = {link.site: link for link in links}
    assert by_site["mobile_de"].error and by_site["kleinanzeigen"].error
    assert by_site["autoscout24"].url


def test_build_links_rejects_unknown_site(profile, cache):
    with pytest.raises(ValueError, match="nope"):
        build_links(profile, fake_client({}), cache, only=["nope"])
