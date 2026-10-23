from __future__ import annotations

import csv
from pathlib import Path

from .models import RawRace
from .utils import normalize_text, stable_int

UF_STATES = {
    "AC": ("Acre", "Norte"), "AL": ("Alagoas", "Nordeste"), "AP": ("Amapá", "Norte"),
    "AM": ("Amazonas", "Norte"), "BA": ("Bahia", "Nordeste"), "CE": ("Ceará", "Nordeste"),
    "DF": ("Distrito Federal", "Centro-Oeste"), "ES": ("Espírito Santo", "Sudeste"),
    "GO": ("Goiás", "Centro-Oeste"), "MA": ("Maranhão", "Nordeste"), "MT": ("Mato Grosso", "Centro-Oeste"),
    "MS": ("Mato Grosso do Sul", "Centro-Oeste"), "MG": ("Minas Gerais", "Sudeste"),
    "PA": ("Pará", "Norte"), "PB": ("Paraíba", "Nordeste"), "PR": ("Paraná", "Sul"),
    "PE": ("Pernambuco", "Nordeste"), "PI": ("Piauí", "Nordeste"), "RJ": ("Rio de Janeiro", "Sudeste"),
    "RN": ("Rio Grande do Norte", "Nordeste"), "RS": ("Rio Grande do Sul", "Sul"),
    "RO": ("Rondônia", "Norte"), "RR": ("Roraima", "Norte"), "SC": ("Santa Catarina", "Sul"),
    "SP": ("São Paulo", "Sudeste"), "SE": ("Sergipe", "Nordeste"), "TO": ("Tocantins", "Norte"),
}


def _write(path: Path, columns: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def export_powerbi(records: list[RawRace], data_dir: Path) -> list[Path]:
    gold = data_dir / "gold"
    locations, organizers, distances = {}, {}, {}
    facts, bridges = [], []
    for record in records:
        race_id = stable_int(f"{record.title_normalized}|{record.start_local}|{record.city}|{record.uf}")
        location_key = f"{normalize_text(record.city)}|{record.uf or ''}"
        location_id = stable_int(location_key, digits=12)
        state, region = UF_STATES.get(record.uf or "", (None, None))
        locations[location_id] = {
            "LocalidadeID": location_id, "Cidade": record.city, "UF": record.uf,
            "Estado": state, "Regiao": region, "Pais": record.country or "Brasil",
            "Latitude": None, "Longitude": None,
        }
        organizer_id = stable_int(normalize_text(record.organizer), digits=12) if record.organizer else None
        if organizer_id:
            organizers[organizer_id] = {
                "OrganizadorID": organizer_id, "Organizador": record.organizer, "Site": None,
                "Instagram": None, "Email": None, "Telefone": None, "CidadeSede": None,
                "UFSede": None, "Ativo": True,
            }
        facts.append({
            "CorridaID": race_id, "NomeCorrida": record.title,
            "DataCorrida": record.start_local.date().isoformat() if record.start_local else None,
            "LocalidadeID": location_id, "OrganizadorID": organizer_id, "CategoriaID": 1,
            "HoraLargada": record.start_local.time().isoformat() if record.start_local else None,
            "LocalLargada": record.address, "ValorMinimo": record.price_min, "ValorMaximo": record.price_max,
            "DataInicioInscricao": None, "DataFimInscricao": None,
            "URLOriginal": record.registration_url or record.source_url, "URLAfiliado": None,
            "URLImagem": record.image_url, "StatusInscricao": _status_pt(record.sales_status),
            "Patrocinado": False, "Destaque": False, "PrioridadeExibicao": None,
            "DataAtualizacao": record.captured_at.isoformat(), "Fonte": record.source_key, "Ativo": True,
        })
        for meters in record.distances_m:
            distance_id = stable_int(str(meters), digits=9)
            distances[distance_id] = {
                "DistanciaID": distance_id, "Distancia": _distance_label(meters),
                "DistanciaKM": round(meters / 1000, 3), "Grupo": _distance_group(meters),
                "OrdemExibicao": meters, "Ativo": True,
            }
            bridges.append({"CorridaID": race_id, "DistanciaID": distance_id})
    outputs = [
        gold / "FatoCorridas.csv", gold / "DimLocalidade.csv", gold / "DimOrganizador.csv",
        gold / "DimDistancia.csv", gold / "PonteCorridaDistancia.csv",
    ]
    _write(outputs[0], ["CorridaID", "NomeCorrida", "DataCorrida", "LocalidadeID", "OrganizadorID", "CategoriaID", "HoraLargada", "LocalLargada", "ValorMinimo", "ValorMaximo", "DataInicioInscricao", "DataFimInscricao", "URLOriginal", "URLAfiliado", "URLImagem", "StatusInscricao", "Patrocinado", "Destaque", "PrioridadeExibicao", "DataAtualizacao", "Fonte", "Ativo"], facts)
    _write(outputs[1], ["LocalidadeID", "Cidade", "UF", "Estado", "Regiao", "Pais", "Latitude", "Longitude"], list(locations.values()))
    _write(outputs[2], ["OrganizadorID", "Organizador", "Site", "Instagram", "Email", "Telefone", "CidadeSede", "UFSede", "Ativo"], list(organizers.values()))
    _write(outputs[3], ["DistanciaID", "Distancia", "DistanciaKM", "Grupo", "OrdemExibicao", "Ativo"], list(distances.values()))
    _write(outputs[4], ["CorridaID", "DistanciaID"], bridges)
    return outputs


def _status_pt(value: str) -> str:
    return {"open": "Aberta", "coming_soon": "Em breve", "sold_out": "Esgotada", "closed": "Encerrada"}.get(value, "A confirmar")


def _distance_label(meters: int) -> str:
    if meters == 21_097:
        return "Meia Maratona"
    if meters == 42_195:
        return "Maratona"
    return f"{meters / 1000:g} km"


def _distance_group(meters: int) -> str:
    return "Curta" if meters <= 5_000 else "Média" if meters <= 15_000 else "Longa"
