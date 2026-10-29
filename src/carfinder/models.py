"""Core data types: what you search for, and what the sites return."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

class Fuel(StrEnum):
    PETROL = "petrol"
    DIESEL = "diesel"
    HYBRID = "hybrid"
    ELECTRIC = "electric"
    LPG = "lpg"


class Gearbox(StrEnum):
    MANUAL = "manual"
    AUTOMATIC = "automatic"


class Range(BaseModel):
    """Inclusive numeric range; either end may be open."""

    min: int | None = Field(None, ge=0)
    max: int | None = Field(None, ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> Range:
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"min ({self.min}) is greater than max ({self.max})")
        return self

    def contains(self, value: int | None) -> bool:
        """Unknown values pass; only a known value outside the range fails."""
        if value is None:
            return True
        return (self.min is None or value >= self.min) and (self.max is None or value <= self.max)

    def label(self, grouped: bool = True) -> str:
        """Human-readable form, e.g. "8,000–10,000" or "≤160,000"; grouped=False for years."""
        fmt = "{:,}" if grouped else "{}"
        if self.min is not None and self.max is not None:
            return f"{fmt.format(self.min)}–{fmt.format(self.max)}"
        if self.max is not None:
            return f"≤{fmt.format(self.max)}"
        if self.min is not None:
            return f"≥{fmt.format(self.min)}"
        return "any"


class Location(BaseModel):
    """Where to search in Germany."""

    zip: str = Field(pattern=r"^\d{4,5}$")
    country: str = Field("DE", pattern=r"^[A-Z]{2}$")
    radius_km: int = Field(200, gt=0, le=1000)


class RoLocation(BaseModel):
    """Where to search in Romania: a city (Autovit's slug, e.g. "cluj-napoca") or the whole country."""

    city: str | None = Field(None, pattern=r"^[a-z0-9-]{2,40}$")
    radius_km: int = Field(100, gt=0, le=1000)


class SearchProfile(BaseModel):
    """One search: loaded from profiles/<name>.yaml or sent as JSON by the web UI."""

    name: str = Field("", max_length=80)
    make: str = Field(min_length=1, max_length=60)
    model: str | None = Field(None, max_length=60)  # None = every model of the make
    year: Range = Range()
    mileage_km: Range = Range()
    price_eur: Range = Range()
    fuel: list[Fuel] = []
    gearbox: list[Gearbox] = []
    location: Location
    ro_location: RoLocation = RoLocation()
    sites: list[str] | None = None
    overrides: dict[str, dict[str, str]] = {}

    @field_validator("model", mode="before")
    @classmethod
    def _blank_model_is_any(cls, value: str | None) -> str | None:
        return value.strip() or None if isinstance(value, str) else value

    @model_validator(mode="after")
    def _safe_overrides(self) -> SearchProfile:
        for site, values in self.overrides.items():
            for key, value in values.items():
                if not (key.isidentifier() and len(value) <= 40 and value.replace("-", "").replace("_", "").isalnum()):
                    raise ValueError(f"invalid override {site}.{key}={value!r}")
        return self

    @property
    def title(self) -> str:
        return self.name or f"{self.make} {self.model or '(all models)'}"

    def query_id(self) -> str:
        """Stable ID for this search, so re-running it updates the same results file."""
        payload = self.model_dump(mode="json", exclude={"name"})
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        return digest[:12]

    def summary(self) -> str:
        parts = [
            f"{self.make} {self.model or '(all models)'}",
            f"year {self.year.label(grouped=False)}",
            f"{self.mileage_km.label()} km",
            f"€{self.price_eur.label()}",
            "/".join(self.fuel) or "any fuel",
            "/".join(self.gearbox) or "any gearbox",
            f"DE: {self.location.radius_km} km around {self.location.zip}",
            f"RO: {self.ro_location.radius_km} km around {self.ro_location.city}"
            if self.ro_location.city
            else "RO: whole country",
        ]
        return " · ".join(parts)


class SearchLink(BaseModel):
    """A pre-filtered search URL for one site, or the reason it couldn't be built."""

    site: str
    name: str
    url: str | None = None
    notes: list[str] = []
    error: str | None = None


class PricePoint(BaseModel):
    at: str
    price_eur: int


class Listing(BaseModel):
    """A single car ad, normalized across sites."""

    source: str
    source_id: str
    country: str = "DE"
    url: str
    title: str
    model: str | None = None
    price_eur: int
    listed_price: int | None = None  # original amount when the ad isn't priced in euros
    listed_currency: str | None = None
    old_price_eur: int | None = None
    negotiable: bool = False
    price_label: str | None = None  # the site's own rating, e.g. AutoScout24 "good-price"
    mileage_km: int | None = None
    year: int | None = None
    first_registration: str | None = None  # "MM/YYYY"
    fuel: Fuel | None = None
    gearbox: Gearbox | None = None
    power_hp: int | None = None
    zip: str | None = None
    city: str | None = None
    distance_km: int | None = None
    seller_type: Literal["dealer", "private"] | None = None
    seller_name: str | None = None
    images: list[str] = []
    # Filled in after fetching:
    also_on: list[SearchLink] = []
    score: int | None = None
    score_parts: list[str] = []  # why the score is what it is, e.g. "€900 below similar cars (+9)"
    flags: list[str] = []
    first_seen: str | None = None
    last_seen: str | None = None
    price_history: list[PricePoint] = []

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"
