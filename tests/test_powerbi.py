import csv
from datetime import datetime, timezone

from race_ingestion.models import RawRace
from race_ingestion.powerbi import export_powerbi


def test_powerbi_export_uses_existing_model_columns(tmp_path):
    item = RawRace(source_key="test", external_id="1", source_url="https://x.test/e/1", title="Corrida Teste", title_normalized="corrida teste", start_local=datetime(2027, 3, 14, 6, 30), city="Belo Horizonte", uf="MG", distances_m=[5_000, 10_000], captured_at=datetime.now(timezone.utc), content_hash="x", parser="test")
    paths = export_powerbi([item], tmp_path)
    with paths[0].open(encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames[:4] == ["CorridaID", "NomeCorrida", "DataCorrida", "LocalidadeID"]
        assert next(reader)["Fonte"] == "test"
