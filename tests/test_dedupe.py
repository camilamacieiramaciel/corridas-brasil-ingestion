from datetime import datetime, timezone

from race_ingestion.dedupe import match
from race_ingestion.models import RawRace


def race(source: str, title: str) -> RawRace:
    return RawRace(source_key=source, external_id=source, source_url=f"https://{source}.test/e/1", title=title, title_normalized=title.lower(), start_local=datetime(2027, 3, 14, 6, 30), city="Belo Horizonte", uf="MG", distances_m=[10_000], captured_at=datetime.now(timezone.utc), content_hash="x", parser="test")


def test_same_event_cross_source_is_merge_candidate():
    result = match(race("a", "Circuito Horizonte Run 10K"), race("b", "Circuito Horizonte Run 10K"))
    assert result.decision == "auto_merge"
    assert result.score >= 0.90
