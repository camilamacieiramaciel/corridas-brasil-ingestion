from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class SourceConfig(BaseModel):
    key: str
    name: str
    start_urls: list[HttpUrl]
    allowed_domains: list[str]
    listing_patterns: list[str] = Field(default_factory=list)
    detail_patterns: list[str] = Field(default_factory=list)
    render: Literal["http", "auto", "browser"] = "http"
    country_filter: str | None = None
    max_discovery_pages: int = 20
    delay_seconds: float = 2.0
    enabled: bool = True


class Snapshot(BaseModel):
    source_key: str
    url: str
    fetched_at: datetime
    status_code: int
    content_type: str = ""
    content_hash: str
    body_path: str
    body: str = Field(exclude=True)


class RawRace(BaseModel):
    source_key: str
    external_id: str
    source_url: str
    registration_url: str | None = None
    title: str
    title_normalized: str
    start_local: datetime | None = None
    timezone: str | None = None
    city: str | None = None
    uf: str | None = None
    country: str | None = "Brasil"
    address: str | None = None
    distances_m: list[int] = Field(default_factory=list)
    organizer: str | None = None
    sales_status: Literal["coming_soon", "open", "sold_out", "closed", "unknown"] = "unknown"
    price_min: float | None = None
    price_max: float | None = None
    currency: str | None = None
    image_url: str | None = None
    captured_at: datetime
    content_hash: str
    parser: str
    quality_flags: list[str] = Field(default_factory=list)


class MatchExplanation(BaseModel):
    score: float
    decision: Literal["auto_merge", "review", "create"]
    name: float
    date: float
    city: float
    distance: float
    organizer: float
    left_source: str
    right_source: str
