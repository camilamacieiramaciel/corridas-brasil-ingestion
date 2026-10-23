from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser

from .models import RawRace, Snapshot, SourceConfig
from .utils import clean_url, normalize_text, sha256_text

UF_PATTERN = r"AC|AL|AP|AM|BA|CE|DF|ES|GO|MA|MT|MS|MG|PA|PB|PR|PE|PI|RJ|RN|RS|RO|RR|SC|SP|SE|TO"
DISTANCE_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[.,]\d{1,2})?)\s*(km|k|metros?|m)\b", re.I)
CITY_UF_RE = re.compile(rf"([A-ZÀ-Ú][\wÀ-ÿ' .-]{{2,60}}?)\s*[-–/]\s*({UF_PATTERN})\b")
DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s+(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-zç]*\s+\d{4})\b",
    re.I,
)


def _iter_jsonld(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from _iter_jsonld(item)
    elif isinstance(value, dict):
        types = value.get("@type", [])
        if isinstance(types, str):
            types = [types]
        if any(str(t).lower() in {"event", "sportsevent"} for t in types):
            yield value
        for key in ("@graph", "itemListElement"):
            if key in value:
                yield from _iter_jsonld(value[key])
        if "item" in value:
            yield from _iter_jsonld(value["item"])


def _jsonld_events(soup: BeautifulSoup) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            events.extend(_iter_jsonld(json.loads(tag.string or tag.get_text())))
        except (json.JSONDecodeError, TypeError):
            continue
    return events


def _address(event: dict[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    location = event.get("location") or {}
    if isinstance(location, list):
        location = location[0] if location else {}
    address = location.get("address", {}) if isinstance(location, dict) else {}
    if isinstance(address, str):
        return None, None, None, address
    return (
        address.get("addressLocality"),
        address.get("addressRegion"),
        address.get("addressCountry"),
        ", ".join(str(address.get(k)) for k in ("streetAddress", "postalCode") if address.get(k)) or None,
    )


def _offer(event: dict[str, Any]) -> tuple[str | None, float | None, float | None, str | None, str]:
    offers = event.get("offers") or []
    if isinstance(offers, dict):
        offers = [offers]
    urls, prices, currency, availability = [], [], None, "unknown"
    for offer in offers:
        if not isinstance(offer, dict):
            continue
        if offer.get("url"):
            urls.append(str(offer["url"]))
        for key in ("price", "lowPrice", "highPrice"):
            try:
                if offer.get(key) is not None:
                    prices.append(float(str(offer[key]).replace(",", ".")))
            except ValueError:
                pass
        currency = currency or offer.get("priceCurrency")
        av = str(offer.get("availability", "")).lower()
        if "instock" in av:
            availability = "open"
        elif "soldout" in av:
            availability = "sold_out"
        elif "preorder" in av:
            availability = "coming_soon"
    return (urls[0] if urls else None, min(prices) if prices else None, max(prices) if prices else None, currency, availability)


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    translated = value.strip().lower()
    months = {
        "janeiro": "january", "jan": "jan", "fevereiro": "february", "fev": "feb",
        "março": "march", "marco": "march", "mar": "mar", "abril": "april", "abr": "apr",
        "maio": "may", "mai": "may", "junho": "june", "jun": "jun", "julho": "july",
        "jul": "jul", "agosto": "august", "ago": "aug", "setembro": "september",
        "set": "sep", "outubro": "october", "out": "oct", "novembro": "november",
        "nov": "nov", "dezembro": "december", "dez": "dec",
    }
    for portuguese, english in sorted(months.items(), key=lambda item: -len(item[0])):
        translated = re.sub(rf"\b{portuguese}\b", english, translated)
    try:
        parsed = dateutil_parser.parse(translated, dayfirst=True, fuzzy=True)
        return parsed.replace(tzinfo=None)
    except (ValueError, OverflowError):
        return None


def _distances(text: str) -> list[int]:
    result: set[int] = set()
    for value, unit in DISTANCE_RE.findall(text):
        number = float(value.replace(",", "."))
        meters = round(number * 1000) if unit.lower() in {"km", "k"} else round(number)
        if 100 <= meters <= 250_000:
            result.add(meters)
    if re.search(r"meia maratona|21k", text, re.I):
        result.add(21_097)
    if re.search(r"\bmaratona\b|42k", text, re.I) and not re.search(r"meia maratona", text, re.I):
        result.add(42_195)
    return sorted(result)


def _external_id(event: dict[str, Any], url: str) -> str:
    candidate = event.get("@id") or event.get("identifier")
    if isinstance(candidate, dict):
        candidate = candidate.get("value")
    return str(candidate or sha256_text(clean_url(url))[:24])


def _make_raw(event: dict[str, Any], snapshot: Snapshot, config: SourceConfig) -> RawRace | None:
    title = str(event.get("name") or event.get("headline") or "").strip()
    if not title:
        return None
    city, uf, country, address = _address(event)
    registration_url, price_min, price_max, currency, status = _offer(event)
    source_url = clean_url(str(event.get("url") or snapshot.url))
    description = str(event.get("description") or "")
    image = event.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    if isinstance(image, dict):
        image = image.get("url")
    organizer = event.get("organizer") or event.get("performer")
    if isinstance(organizer, dict):
        organizer = organizer.get("name")
    quality = []
    start = _parse_date(str(event.get("startDate") or ""))
    if not start:
        quality.append("missing_start_date")
    if not city:
        quality.append("missing_city")
    if config.country_filter and country and normalize_text(country) != normalize_text(config.country_filter):
        return None
    return RawRace(
        source_key=config.key,
        external_id=_external_id(event, source_url),
        source_url=source_url,
        registration_url=clean_url(registration_url) if registration_url else None,
        title=title,
        title_normalized=normalize_text(title),
        start_local=start,
        timezone="America/Sao_Paulo" if (country or "Brasil").lower() in {"br", "brasil", "brazil"} else None,
        city=city,
        uf=uf,
        country=country or config.country_filter or "Brasil",
        address=address,
        distances_m=_distances(f"{title} {description}"),
        organizer=str(organizer).strip() if organizer else None,
        sales_status=status,
        price_min=price_min,
        price_max=price_max,
        currency=currency,
        image_url=str(image) if image else None,
        captured_at=snapshot.fetched_at,
        content_hash=snapshot.content_hash,
        parser="jsonld",
        quality_flags=quality,
    )


def _fallback(snapshot: Snapshot, config: SourceConfig, soup: BeautifulSoup) -> RawRace | None:
    if not any(re.search(pattern, snapshot.url, re.I) for pattern in config.detail_patterns):
        return None
    title_tag = soup.select_one("h1") or soup.select_one('meta[property="og:title"]') or soup.title
    title = (title_tag.get("content") if title_tag and title_tag.name == "meta" else title_tag.get_text(" ", strip=True) if title_tag else "")
    if not title:
        return None
    text = soup.get_text(" ", strip=True)
    date_match = DATE_RE.search(text)
    city_match = CITY_UF_RE.search(text)
    registration = None
    for a in soup.select("a[href]"):
        label = normalize_text(a.get_text(" ", strip=True))
        if any(term in label for term in ("inscreva", "inscricao", "comprar", "garanta")):
            registration = clean_url(urljoin(snapshot.url, a["href"]))
            break
    start = _parse_date(date_match.group(0)) if date_match else None
    flags = []
    if not start:
        flags.append("missing_start_date")
    if not city_match:
        flags.append("missing_city")
    return RawRace(
        source_key=config.key,
        external_id=sha256_text(clean_url(snapshot.url))[:24],
        source_url=clean_url(snapshot.url),
        registration_url=registration,
        title=title.strip(),
        title_normalized=normalize_text(title),
        start_local=start,
        timezone="America/Sao_Paulo",
        city=city_match.group(1).strip() if city_match else None,
        uf=city_match.group(2) if city_match else None,
        country="Brasil",
        distances_m=_distances(text),
        captured_at=snapshot.fetched_at,
        content_hash=snapshot.content_hash,
        parser="html_fallback",
        quality_flags=flags,
    )


def parse_races(snapshot: Snapshot, config: SourceConfig) -> list[RawRace]:
    soup = BeautifulSoup(snapshot.body, "html.parser")
    races = [race for event in _jsonld_events(soup) if (race := _make_raw(event, snapshot, config))]
    if not races:
        fallback = _fallback(snapshot, config, soup)
        if fallback:
            races.append(fallback)
    unique: dict[tuple[str, str], RawRace] = {}
    for race in races:
        unique[(race.source_key, race.external_id)] = race
    return list(unique.values())


def discover_links(html: str, base_url: str, config: SourceConfig) -> tuple[set[str], set[str]]:
    soup = BeautifulSoup(html, "html.parser")
    listing, detail = set(), set()
    for tag in soup.select("a[href]"):
        url = clean_url(urljoin(base_url, tag.get("href", "")))
        if not url.startswith(("http://", "https://")):
            continue
        if any(re.search(pattern, url, re.I) for pattern in config.detail_patterns):
            detail.add(url)
        elif any(re.search(pattern, url, re.I) for pattern in config.listing_patterns):
            listing.add(url)
    return listing, detail
