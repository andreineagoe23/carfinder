import httpx
import pytest

from carfinder.cache import Cache
from carfinder.models import SearchProfile


@pytest.fixture
def profile() -> SearchProfile:
    return SearchProfile.model_validate(
        {
            "name": "Mazda CX-3",
            "make": "Mazda",
            "model": "CX-3",
            "year": {"min": 2015, "max": 2017},
            "mileage_km": {"max": 160000},
            "price_eur": {"min": 8000, "max": 10000},
            "fuel": ["petrol"],
            "location": {"zip": "93339", "country": "DE", "radius_km": 200},
        }
    )


@pytest.fixture
def cache(tmp_path) -> Cache:
    return Cache(tmp_path / "lookups.json")


def fake_client(routes: dict[str, object]) -> httpx.Client:
    """httpx client that answers JSON from `routes` keyed by URL path; 404 otherwise."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path in routes:
            return httpx.Response(200, json=routes[request.url.path])
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))
