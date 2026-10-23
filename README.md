# Ingestão Corridas Brasil — Git + Python

Repositório pronto para Git/GitHub com **10 conectores**: Running Life, Corridas BR, Ahotu, Ticket Sports, Ativo, Minhas Inscrições, Portal das Corridas, Corridinhas, Só Corridas e Road Runners.

A arquitetura segue `discover → fetch → snapshot → parse → normalize → dedupe → export`. Ela preserva HTML bruto por hash, gera rastreabilidade por fonte e exporta CSVs compatíveis com o modelo Power BI/Fabric existente.

## Saídas

- `data/raw/<fonte>/`: snapshots HTML identificados por SHA-256.
- `data/bronze/source_records.jsonl`: registros por fonte, sem mesclar.
- `data/silver/races.csv`: catálogo canônico após deduplicação.
- `data/quality/ingestion_report.json`: páginas, registros e erros por fonte.
- `data/quality/dedupe_review.json`: candidatos ambíguos para curadoria.
- `data/gold/FatoCorridas.csv`, `DimLocalidade.csv`, `DimOrganizador.csv`, `DimDistancia.csv` e `PonteCorridaDistancia.csv`: carga pronta para Power BI/Fabric.
- `data/private/`: resultados pessoais Road Runners; sempre excluído do Git.

## Início rápido

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\\Scripts\\activate
pip install -e ".[dev,browser]"
playwright install chromium
cp .env.example .env
python -m race_ingestion.cli validate
python -m race_ingestion.cli list-sources
pytest -q
```

Executar uma fonte:

```bash
python -m race_ingestion.cli run --source roadrunners --max-event-pages 20
```

Executar todas:

```bash
python -m race_ingestion.cli run --all --max-event-pages 100
```

## Road Runners: catálogo público x perfil pessoal

O conector público usa as buscas de eventos/resultados e páginas `/evento/`. A URL de correspondência de atleta pode exigir login e contém dado pessoal; por isso **não fica em `sources.yml` nem é commitada**.

Para importar seus resultados localmente:

```bash
export ROADRUNNERS_PROFILE_URL='https://roadrunners.run/?requerlogin=...'
export ROADRUNNERS_COOKIE='cookie_de_sessao_se_necessario'
python -m race_ingestion.cli athlete-results
```

O comando não contorna login, CAPTCHA nem bloqueios. Se a sessão não estiver válida ou o layout mudar, encerra com erro e não publica dados incompletos.

## GitHub Actions

- `ci.yml`: valida configuração, lint e testes a cada push/PR.
- `ingest.yml`: execução diária e manual; publica as camadas bronze/silver/gold como artefato do workflow.
- Configure `INGESTION_USER_AGENT` em **Settings → Secrets and variables → Actions → Variables** com contato operacional real.
- Não coloque `ROADRUNNERS_PROFILE_URL` ou cookie no workflow público; se automatizar dados pessoais, use um workflow privado separado e secrets, sem upload de artefato público.

## Regras operacionais

1. Respeitar `robots.txt`, rate limit, termos de uso e contratos de cada fonte.
2. Preferir API/feed ou parceria; scraping técnico não equivale a autorização comercial.
3. Não versionar snapshots, dados coletados ou dados pessoais no Git.
4. Revisar seletores e fixtures quando a contagem cair ou o parser gerar flags.
5. Tratar páginas dinâmicas com Playwright somente quando HTTP/JSON-LD não bastar.
6. Não assumir que uma fonte é sempre a verdade; conflitos ficam na fila de revisão.

## Limites conhecidos

Sites dinâmicos alteram seletores e podem exigir autenticação, CAPTCHA ou API interna. Os conectores são defensivos: tentam JSON-LD primeiro, usam fallback HTML, mantêm snapshots e registram falhas por página. Antes de produção, execute uma carga por fonte, rotule uma amostra e ajuste padrões/seletores no `config/sources.yml`.
