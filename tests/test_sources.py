from pathlib import Path

from race_ingestion.pipeline import load_sources


def test_all_ten_sources_are_registered():
    sources = load_sources(Path("config/sources.yml"))
    assert len(sources) == 10
    assert "roadrunners" in {s.key for s in sources}
