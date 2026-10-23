from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .utils import clean_url, normalize_text, sha256_text


def import_private_results(data_dir: Path, profile_url: str | None = None, cookie: str | None = None) -> Path:
    """Importa resultados pessoais fora das camadas públicas e fora do Git.

    A URL de perfil e o cookie devem vir de secret/variável de ambiente. Não contorna login,
    CAPTCHA ou bloqueios: se a sessão não for válida, encerra com erro explícito.
    """
    profile_url = profile_url or os.getenv("ROADRUNNERS_PROFILE_URL")
    cookie = cookie or os.getenv("ROADRUNNERS_COOKIE")
    if not profile_url:
        raise ValueError("Defina ROADRUNNERS_PROFILE_URL; não grave a URL pessoal no repositório.")
    headers = {"User-Agent": os.getenv("INGESTION_USER_AGENT", "CorridasBrasilBot/0.1")}
    if cookie:
        headers["Cookie"] = cookie
    response = httpx.get(profile_url, headers=headers, follow_redirects=True, timeout=30)
    response.raise_for_status()
    if "entrar" in normalize_text(response.text[:8000]) and not cookie:
        raise PermissionError("O perfil exige sessão. Configure ROADRUNNERS_COOKIE como secret.")
    soup = BeautifulSoup(response.text, "html.parser")
    rows = []
    selectors = "[data-result], .result-card, .resultado-item, table tbody tr"
    for node in soup.select(selectors):
        text = " ".join(node.get_text(" ", strip=True).split())
        if len(text) < 8:
            continue
        link = node.select_one("a[href]")
        date = re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", text)
        distance = re.search(r"\b\d{1,3}(?:[.,]\d+)?\s*(?:km|k)\b", text, re.I)
        time_value = re.search(r"\b\d{1,2}:\d{2}:\d{2}\b", text)
        rows.append({
            "source": "roadrunners_private_profile",
            "result_id": sha256_text(text)[:24],
            "event_url": clean_url(urljoin(str(response.url), link["href"])) if link else None,
            "date_text": date.group(0) if date else None,
            "distance_text": distance.group(0) if distance else None,
            "finish_time_text": time_value.group(0) if time_value else None,
            "raw_text": text,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        })
    if not rows:
        raise RuntimeError("Nenhum resultado foi identificado; a página pode exigir login ou ter mudado de layout.")
    target = data_dir / "private" / "roadrunners_athlete_results.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return target
