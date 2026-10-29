from pathlib import Path

import pytest
from pydantic import ValidationError

from carfinder.models import SearchProfile
from carfinder.profiles import list_profiles, load_profile

REPO_PROFILES = Path(__file__).parent.parent / "profiles"


def test_bundled_profiles_load():
    names = list_profiles(REPO_PROFILES)
    assert "mazda-cx3" in names
    for name in names:
        load_profile(REPO_PROFILES, name)


def test_missing_profile_lists_available():
    with pytest.raises(FileNotFoundError, match="mazda-cx3"):
        load_profile(REPO_PROFILES, "nope")


def test_inverted_range_rejected():
    with pytest.raises(ValidationError, match="greater than max"):
        SearchProfile.model_validate(
            {"name": "x", "make": "x", "model": "x", "year": {"min": 2018, "max": 2015},
             "location": {"zip": "93339"}}
        )


def test_unknown_fuel_rejected():
    with pytest.raises(ValidationError):
        SearchProfile.model_validate(
            {"name": "x", "make": "x", "model": "x", "fuel": ["steam"], "location": {"zip": "93339"}}
        )


def test_summary_formats_years_without_grouping():
    summary = load_profile(REPO_PROFILES, "mazda-cx3").summary()
    assert "year 2015–2017" in summary
    assert "≤160,000 km" in summary
