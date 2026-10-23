# Matriz de fontes

| Chave | Fonte | Entrada pública | Estratégia inicial | Observação |
|---|---|---|---|---|
| `running_life` | Running Life | Calendário Brasil | HTTP + JSON-LD/HTML; paginação; detalhe `/pt/event/` | Fonte nacional paginada. |
| `corridasbr` | Corridas BR | Índice por UF | HTTP; calendários estaduais `.asp` | Descoberta em dois níveis. |
| `ahotu` | Ahotu | Corrida | HTTP/Playwright automático; detalhe `/pt-BR/evento/` | Filtro de país aplicado quando o país está explícito. |
| `ticketsports` | Ticket Sports | Calendário/filtros | Playwright automático + JSON-LD | Confirmar API/feed ou autorização antes de escala. |
| `ativo` | Ativo | Calendário | Playwright automático + JSON-LD/HTML | O portal também contém conteúdo editorial; só padrões de evento entram. |
| `minhas_inscricoes` | Minhas Inscrições | Calendário corrida de rua | Playwright automático; redirecionamentos de evento | Preserva URL original e de inscrição. |
| `portal_das_corridas` | Portal das Corridas | Eventos | Playwright automático; `/event-details/` | Página de evento é a unidade de coleta. |
| `corridinhas` | Corridinhas | `/races` | Playwright automático; detalhe de corrida | Seletor isolado por padrão de URL. |
| `so_corridas` | Só Corridas | `/corridas/` | HTTP + JSON-LD/HTML; estado/cidade | Mantém rate limit por domínio. |
| `roadrunners` | Road Runners | Busca de eventos e resultados | Playwright automático; `/evento/` | Perfil pessoal é fluxo separado e privado. |

## Critérios de aceite por conector

1. Ao menos uma fixture regressiva sem dado pessoal.
2. `external_id`, `source_url`, título, captura e hash sempre preenchidos.
3. Datas e localidades ausentes geram `quality_flags`, nunca valores inventados.
4. Queda anormal de volume ou erro de layout aparece em `ingestion_report.json`.
5. Mudança de fonte ou conflito de evento permanece rastreável na fila de revisão.
6. Produção somente após conferência de `robots.txt`, termos, contrato/API e limite de requisições.
