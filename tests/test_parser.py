from datetime import datetime, timezone
from pathlib import Path

from race_ingestion.models import Snapshot, SourceConfig
from race_ingestion.parser import parse_races
from race_ingestion.utils import sha256_text


def test_jsonld_event_is_parsed():
    body = Path("tests/fixtures/event.html").read_text(encoding="utf-8")
    config = SourceConfig(key="test", name="Test", start_urls=["https://example.org"], allowed_domains=["example.org"], detail_patterns=["/evento/"])
    snapshot = Snapshot(source_key="test", url="https://example.org/evento/123", fetched_at=datetime.now(timezone.utc), status_code=200, content_hash=sha256_text(body), body_path="fixture", body=body)
    races = parse_races(snapshot, config)
    assert len(races) == 1
    assert races[0].city == "Belo Horizonte"
    assert races[0].uf == "MG"
    assert 10_000 in races[0].distances_m
    assert races[0].sales_status == "open"
