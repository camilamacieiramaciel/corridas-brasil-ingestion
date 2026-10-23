from __future__ import annotations

import json
import logging
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from .http import RespectfulClient
from .models import RawRace, Snapshot, SourceConfig
from .parser import discover_links, parse_races
from .utils import clean_url, sha256_text

LOG = logging.getLogger(__name__)


def load_sources(path: Path) -> list[SourceConfig]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [SourceConfig.model_validate(item) for item in payload["sources"]]


def _snapshot(client: RespectfulClient, config: SourceConfig, url: str, data_dir: Path) -> Snapshot:
    result = client.fetch(url, delay_seconds=config.delay_seconds, render=config.render)
    digest = sha256_text(result.text)
    raw_dir = data_dir / "raw" / config.key
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_dir / f"{digest}.html"
    if not path.exists():
        path.write_text(result.text, encoding="utf-8")
    return Snapshot(
        source_key=config.key,
        url=clean_url(result.url),
        fetched_at=datetime.now(timezone.utc),
        status_code=result.status_code,
        content_type=result.content_type,
        content_hash=digest,
        body_path=str(path),
        body=result.text,
    )


def run_source(
    config: SourceConfig,
    data_dir: Path,
    max_event_pages: int = 100,
    client: RespectfulClient | None = None,
) -> tuple[list[RawRace], dict]:
    own_client = client is None
    client = client or RespectfulClient()
    queue = deque(str(url) for url in config.start_urls)
    seen_listing: set[str] = set()
    detail_urls: set[str] = set()
    snapshots: list[Snapshot] = []
    errors: list[dict] = []
    races: list[RawRace] = []
    try:
        while queue and len(seen_listing) < config.max_discovery_pages:
            url = clean_url(queue.popleft())
            if url in seen_listing:
                continue
            seen_listing.add(url)
            try:
                snap = _snapshot(client, config, url, data_dir)
                snapshots.append(snap)
                races.extend(parse_races(snap, config))
                listing, details = discover_links(snap.body, snap.url, config)
                detail_urls.update(details)
                for candidate in sorted(listing):
                    if candidate not in seen_listing and _allowed_domain(candidate, config):
                        queue.append(candidate)
            except Exception as exc:  # job deve continuar por fonte/página
                LOG.warning("%s: %s", url, exc)
                errors.append({"url": url, "error": type(exc).__name__, "message": str(exc)})
        for url in sorted(detail_urls)[:max_event_pages]:
            try:
                snap = _snapshot(client, config, url, data_dir)
                snapshots.append(snap)
                races.extend(parse_races(snap, config))
            except Exception as exc:
                LOG.warning("%s: %s", url, exc)
                errors.append({"url": url, "error": type(exc).__name__, "message": str(exc)})
    finally:
        if own_client:
            client.close()
    unique = {(r.source_key, r.external_id, r.content_hash): r for r in races}
    result = list(unique.values())
    report = {
        "source": config.key,
        "listing_pages": len(seen_listing),
        "detail_links_found": len(detail_urls),
        "snapshots": len(snapshots),
        "records": len(result),
        "errors": errors,
        "run_at": datetime.now(timezone.utc).isoformat(),
    }
    return result, report


def _allowed_domain(url: str, config: SourceConfig) -> bool:
    host = urlsplit(url).netloc.lower()
    return any(host == domain or host.endswith(f".{domain}") for domain in config.allowed_domains)


def persist_bronze(records: list[RawRace], data_dir: Path) -> Path:
    target = data_dir / "bronze" / "source_records.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for record in sorted(records, key=lambda r: (r.source_key, r.external_id)):
            handle.write(record.model_dump_json() + "\n")
    return target


def persist_reports(reports: list[dict], data_dir: Path) -> Path:
    target = data_dir / "quality" / "ingestion_report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
