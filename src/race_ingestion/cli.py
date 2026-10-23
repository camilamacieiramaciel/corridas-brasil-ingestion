from __future__ import annotations

import json
import logging
from pathlib import Path

import typer

from .dedupe import canonicalize, persist_silver
from .pipeline import load_sources, persist_bronze, persist_reports, run_source
from .powerbi import export_powerbi
from .roadrunners_private import import_private_results

app = typer.Typer(no_args_is_help=True, help="Ingestão de corridas do Brasil")
DEFAULT_CONFIG = Path("config/sources.yml")
DEFAULT_DATA = Path("data")


@app.command()
def list_sources(config: Path = DEFAULT_CONFIG) -> None:
    """Lista conectores configurados."""
    for source in load_sources(config):
        typer.echo(f"{source.key:22} {'ON' if source.enabled else 'OFF'}  {source.name}")


@app.command()
def run(
    source: list[str] = typer.Option(None, "--source", "-s", help="Chave da fonte; repita a opção."),
    all_sources: bool = typer.Option(False, "--all", help="Executar todas as fontes habilitadas."),
    config: Path = DEFAULT_CONFIG,
    data_dir: Path = DEFAULT_DATA,
    max_event_pages: int = typer.Option(100, min=1, max=5000),
) -> None:
    """Executa fetch, snapshot, parsing, dedupe e exportação Power BI."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    configs = load_sources(config)
    selected = [c for c in configs if c.enabled and (all_sources or c.key in (source or []))]
    if not selected:
        raise typer.BadParameter("Use --all ou ao menos um --source válido.")
    records, reports = [], []
    for item in selected:
        typer.echo(f"\n[{item.key}] iniciando")
        result, report = run_source(item, data_dir, max_event_pages=max_event_pages)
        records.extend(result)
        reports.append(report)
        typer.echo(f"[{item.key}] {report['records']} registros; {len(report['errors'])} erros")
    persist_bronze(records, data_dir)
    canonical, review = canonicalize(records)
    persist_silver(canonical, review, data_dir)
    export_powerbi(canonical, data_dir)
    persist_reports(reports, data_dir)
    typer.echo(f"\nConcluído: {len(records)} registros-fonte; {len(canonical)} canônicos; {len(review)} para revisão.")


@app.command("athlete-results")
def athlete_results(data_dir: Path = DEFAULT_DATA) -> None:
    """Importa resultados pessoais Road Runners usando secrets locais/CI."""
    target = import_private_results(data_dir)
    typer.echo(f"Resultados privados gravados em {target}. O diretório está excluído do Git.")


@app.command()
def validate(config: Path = DEFAULT_CONFIG) -> None:
    """Valida configuração e a presença das dez fontes solicitadas."""
    sources = load_sources(config)
    expected = {"running_life", "corridasbr", "ahotu", "ticketsports", "ativo", "minhas_inscricoes", "portal_das_corridas", "corridinhas", "so_corridas", "roadrunners"}
    actual = {s.key for s in sources}
    if actual != expected:
        raise typer.Exit(f"Fontes divergentes. Faltam={expected-actual}; extras={actual-expected}", code=1)
    typer.echo(json.dumps({"valid": True, "sources": len(sources)}, ensure_ascii=False))


if __name__ == "__main__":
    app()
