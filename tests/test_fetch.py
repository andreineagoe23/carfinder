from pathlib import Path

import httpx

from carfinder.models import Fuel, Gearbox
from carfinder.sites.autoscout24 import AutoScout24
from carfinder.sites.kleinanzeigen import Kleinanzeigen

FIXTURES = Path(__file__).parent / "fixtures"


def test_autoscout24_parse_page(profile, cache):
    html = (FIXTURES / "autoscout24_page.html").read_text()
    listings, has_more = AutoScout24(None, cache).parse_page(html, profile)
    assert has_more
    assert len(listings) == 3
    car = listings[0]
    assert car.source == "autoscout24"
    assert car.url.startswith("https://www.autoscout24.de/angebote/")
    assert car.price_eur == 13690
    assert car.mileage_km == 76540
    assert (car.year, car.first_registration) == (2016, "04/2016")
    assert car.fuel == Fuel.PETROL and car.gearbox == Gearbox.MANUAL
    assert car.power_hp == 120
    assert car.seller_type == "dealer"
    assert car.distance_km == 86
    assert car.images[0].endswith("/480x360.webp")


def test_kleinanzeigen_parse_page_only_reads_result_table(profile, cache):
    html = (FIXTURES / "kleinanzeigen_page.html").read_text()
    listings, has_more = Kleinanzeigen(None, cache).parse_page(html, profile)
    assert has_more
    assert [x.source_id for x in listings] == ["3546601879", "3538845277", "3556065049"]
    car = listings[0]
    assert (car.price_eur, car.old_price_eur, car.negotiable) == (4499, 4999, True)
    assert (car.mileage_km, car.year, car.first_registration) == (179000, 2014, "10/2014")
    assert (car.zip, car.city, car.distance_km) == ("86399", "Bobingen", 101)
    assert car.fuel == Fuel.PETROL  # single-fuel search implies the fuel
    assert "rule=$_59." in car.images[0]


def test_kleinanzeigen_page_url():
    site = Kleinanzeigen(None, None)
    url = "https://www.kleinanzeigen.de/s-autos/93339/preis:8000:10000/c216l6234r200+autos.marke_s:mazda"
    assert site.page_url(url, 1) == url
    assert site.page_url(url, 3) == (
        "https://www.kleinanzeigen.de/s-autos/93339/preis:8000:10000/seite:3/c216l6234r200+autos.marke_s:mazda"
    )


def test_fetch_follows_pages_and_drops_mismatches(profile, cache, monkeypatch):
    monkeypatch.setattr("carfinder.sites.base.PAGE_DELAY_S", 0)
    html = (FIXTURES / "autoscout24_page.html").read_text()
    pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        pages.append(request.url.params.get("page"))
        return httpx.Response(200, text=html.replace('"page": "1"', f'"page": "{len(pages)}"'))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    listings = AutoScout24(client, cache).fetch(profile, max_pages=5)
    assert pages == ["1", "2"]  # fixture says 2 pages in total
    # The fixture's cars cost more than the profile's €10,000 cap, so all are filtered out.
    assert listings == []
