from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from rapidfuzz.fuzz import ratio

from .models import MatchExplanation, RawRace
from .utils import normalize_text


def _date_score(a: datetime | None, b: datetime | None) -> float:
    if not a or not b:
        return 0.0
    hours = abs((a - b).total_seconds()) / 3600
    return max(0.0, 1.0 - hours / 48.0)


def _jaccard(a: list[int], b: list[int]) -> float:
    if not a or not b:
        return 0.0
    left, right = set(a), set(b)
    return len(left & right) / len(left | right)


def match(a: RawRace, b: RawRace) -> MatchExplanation:
    name = ratio(a.title_normalized, b.title_normalized) / 100
    date = _date_score(a.start_local, b.start_local)
    city = 1.0 if a.uf and b.uf and normalize_text(a.city) == normalize_text(b.city) and a.uf == b.uf else 0.0
    distance = _jaccard(a.distances_m, b.distances_m)
    organizer = ratio(normalize_text(a.organizer), normalize_text(b.organizer)) / 100 if a.organizer and b.organizer else 0.0
    score = 0.40 * name + 0.25 * date + 0.15 * city + 0.10 * distance + 0.10 * organizer
    years_conflict = a.start_local and b.start_local and a.start_local.year != b.start_local.year
    cities_conflict = a.city and b.city and (normalize_text(a.city), a.uf) != (normalize_text(b.city), b.uf)
    if years_conflict or cities_conflict:
        decision = "create"
    elif score >= 0.90:
        decision = "auto_merge"
    elif score >= 0.70:
        decision = "review"
    else:
        decision = "create"
    return MatchExplanation(
        score=round(score, 4), decision=decision, name=round(name, 4), date=round(date, 4),
        city=city, distance=round(distance, 4), organizer=round(organizer, 4),
        left_source=a.source_key, right_source=b.source_key,
    )


def canonicalize(records: list[RawRace]) -> tuple[list[RawRace], list[dict]]:
    canonical: list[RawRace] = []
    review: list[dict] = []
    for candidate in sorted(records, key=lambda r: (r.start_local or datetime.max, r.title_normalized)):
        merged = False
        for index, existing in enumerate(canonical):
            if candidate.source_key == existing.source_key:
                continue
            result = match(existing, candidate)
            if result.decision == "auto_merge":
                canonical[index] = choose_better(existing, candidate)
                merged = True
                break
            if result.decision == "review":
                review.append({
                    "left": existing.model_dump(mode="json"),
                    "right": candidate.model_dump(mode="json"),
                    "match": result.model_dump(mode="json"),
                })
        if not merged:
            canonical.append(candidate)
    return canonical, review


def choose_better(a: RawRace, b: RawRace) -> RawRace:
    def completeness(r: RawRace) -> tuple[int, int]:
        fields = (r.start_local, r.city, r.uf, r.organizer, r.registration_url, r.image_url)
        return sum(v is not None for v in fields) + len(r.distances_m), -len(r.quality_flags)
    return a if completeness(a) >= completeness(b) else b


def persist_silver(canonical: list[RawRace], review: list[dict], data_dir: Path) -> tuple[Path, Path]:
    silver = data_dir / "silver" / "races.csv"
    quality = data_dir / "quality" / "dedupe_review.json"
    silver.parent.mkdir(parents=True, exist_ok=True)
    quality.parent.mkdir(parents=True, exist_ok=True)
    columns = list(RawRace.model_fields)
    with silver.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in canonical:
            row = record.model_dump(mode="json")
            row["distances_m"] = json.dumps(row["distances_m"], ensure_ascii=False)
            row["quality_flags"] = json.dumps(row["quality_flags"], ensure_ascii=False)
            writer.writerow(row)
    quality.write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    return silver, quality
