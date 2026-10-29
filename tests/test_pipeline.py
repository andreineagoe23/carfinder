from datetime import date

import httpx

from carfinder.dedupe import dedupe
from carfinder.models import Listing
from carfinder.notify import format_message
from carfinder.scoring import score
from carfinder.search import run_search
from carfinder.store import Store


def car(source="autoscout24", source_id="1", price=9000, km=100_000, year=2016, **kw) -> Listing:
    return Listing(
        source=source,
        source_id=source_id,
        url=f"https://example.test/{source}/{source_id}",
        title=kw.pop("title", "Mazda CX-3"),
        price_eur=price,
        mileage_km=km,
        year=year,
        zip=kw.pop("zip", "90552"),
        images=kw.pop("images", ["https://example.test/img.jpg"]),
        **kw,
    )


def test_dedupe_merges_same_car_across_sites():
    a = car("autoscout24", "a", price=9500, km=100_000)
    b = car("kleinanzeigen", "b", price=9300, km=100_400)
    c = car("kleinanzeigen", "c", price=9300, km=150_000)
    kept = dedupe([b, a, c])
    assert [x.source_id for x in kept] == ["a", "c"]
    assert kept[0].also_on[0].url.endswith("/kleinanzeigen/b")
    assert any("Cheaper on Kleinanzeigen" in f for f in kept[0].flags)


def test_dedupe_drops_repeated_ads_from_same_site():
    a = car("kleinanzeigen", "same")
    assert len(dedupe([a, a.model_copy()])) == 1


def test_score_flags_damage_words_in_title():
    hail = car(source_id="hail", title="Mazda CX3 Top Ausstattung Hagelschaden")
    [scored] = score([hail], today=date(2026, 10, 1))
    assert any("schaden" in f for f in scored.flags)


def test_dedupe_keeps_cars_with_different_registration_month():
    a = car("autoscout24", "a", first_registration="06/2016")
    b = car("kleinanzeigen", "b", first_registration="02/2016")
    assert len(dedupe([a, b])) == 2


def test_score_prefers_cheaper_and_lower_mileage():
    listings = [
        car(source_id="cheap", price=8000, km=60_000),
        car(source_id="mid1", price=9500, km=100_000),
        car(source_id="mid2", price=9600, km=100_000),
        car(source_id="mid3", price=9700, km=100_000),
        car(source_id="pricey", price=11000, km=150_000),
    ]
    ranked = score(listings, today=date(2026, 10, 1))
    assert ranked[0].source_id == "cheap"
    assert ranked[-1].source_id == "pricey"
    assert all(0 <= x.score <= 100 for x in ranked)


def test_score_flags_suspiciously_cheap_and_private():
    listings = [car(source_id=str(i), price=10_000) for i in range(4)]
    listings.append(car(source_id="scam", price=5000, seller_type="private"))
    flagged = next(x for x in score(listings, today=date(2026, 10, 1)) if x.source_id == "scam")
    assert any("below similar cars" in f for f in flagged.flags)
    assert any("Private seller" in f for f in flagged.flags)


def test_run_search_tracks_new_listings_and_price_history(profile, cache, tmp_path, monkeypatch):
    runs = iter([
        [car(source_id="1", price=9800)],
        [car(source_id="1", price=9400), car(source_id="2", price=9900, km=90_000)],
    ])
    monkeypatch.setattr("carfinder.sites.autoscout24.AutoScout24.fetch", lambda self, p, n: next(runs))
    profile.sites = ["autoscout24"]
    store = Store(tmp_path)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))

    first = run_search(profile, client, cache, store, at="2026-10-01T00:00:00Z")
    assert len(first.new_listings) == 1

    second = run_search(profile, client, cache, store, at="2026-10-02T00:00:00Z")
    by_id = {x.source_id: x for x in second.listings}
    assert [x.source_id for x in second.new_listings] == ["2"]
    assert by_id["1"].first_seen == "2026-10-01T00:00:00Z"
    assert [p.price_eur for p in by_id["1"].price_history] == [9800, 9400]
    assert any("Price dropped" in f for f in by_id["1"].flags)

    index = (tmp_path / "index.json").read_text()
    assert first.id in index and '"new_count": 1' in index


def test_failed_site_keeps_previous_listings(profile, cache, tmp_path, monkeypatch):
    profile.sites = ["autoscout24"]
    store = Store(tmp_path)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    monkeypatch.setattr("carfinder.sites.autoscout24.AutoScout24.fetch", lambda self, p, n: [car()])
    run_search(profile, client, cache, store, at="2026-10-01T00:00:00Z")

    def boom(self, p, n):
        raise httpx.ConnectError("blocked")

    monkeypatch.setattr("carfinder.sites.autoscout24.AutoScout24.fetch", boom)
    result = run_search(profile, client, cache, store, at="2026-10-02T00:00:00Z")
    assert "blocked" in result.errors["autoscout24"]
    assert len(result.listings) == 1 and result.new_listings == []


def test_store_delete(profile, cache, tmp_path, monkeypatch):
    monkeypatch.setattr("carfinder.sites.autoscout24.AutoScout24.fetch", lambda self, p, n: [])
    profile.sites = ["autoscout24"]
    store = Store(tmp_path)
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    result = run_search(profile, client, cache, store)
    assert store.delete(result.id)
    assert store.all() == []
    assert (tmp_path / "index.json").read_text().strip() == "[]"


def test_telegram_message_lists_new_cars(profile, cache, tmp_path, monkeypatch):
    monkeypatch.setattr("carfinder.sites.autoscout24.AutoScout24.fetch", lambda self, p, n: [car()])
    profile.sites = ["autoscout24"]
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    result = run_search(profile, client, cache, Store(tmp_path))
    message = format_message(result)
    assert "1 new" in message and "€9,000" in message and 'href="https://example.test/' in message
