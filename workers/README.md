# DECIFRA — Workers de dados/IA (Python)

Workers que alimentam o **golden record** e as camadas anexas. Comunicam com o
mesmo Postgres da app web. Mantidos separados porque o ingestão/matching/IA é
onde o Python é mais forte (ver blueprint §7).

> **Estado:** scaffold. A fatia vertical da v1 (app `web/`) já lê tudo da BD com
> dados seed. Estes workers são a base para ligar fontes reais (EAN APIs, Icecat,
> feeds Awin, fontes de review) nas fases seguintes.

## Pipelines (blueprint §3)

| Pipeline | Gatilho | Função |
|---|---|---|
| `ingest_by_ean` | On-demand (cache-first) | EAN API → Icecat/feeds → fontes de review → **entity resolution** → golden record. |
| `refresh_price_live` | Botão "atualizar" | Google Shopping (SerpApi/Bright Data) → atualiza `offers`. Pago: só on-demand. |
| `feed_batch` | Cron diário | Importa feeds Awin (preço, imagem, deep link) → `offers` em massa. |
| `score_recompute_month` | Cron, dia 10 | Recalcula `scores` + snapshots `rankings` (mês) das categorias com `rankings_enabled`. |
| `score_recompute_year` | Cron, início de janeiro | Snapshots `rankings` (ano anterior). |
| `review_refresh` | Cron por popularidade | Re-busca agregados das fontes para os produtos mais vistos. |

Cada execução grava em `ingestion_runs` (auditoria + frescura visível).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # DATABASE_URL, ANTHROPIC_API_KEY, ...
```

**Regra de ouro:** a IA (Claude) explica, normaliza e raciocina — **nunca** é a
fonte primária dos números. Tudo o que é facto leva `source_id` e `confidence`.
