# DECIFRA — Workers de dados/IA (Python)

Workers que alimentam o **golden record** e as camadas anexas. Comunicam com o
mesmo Postgres da app web. Mantidos separados porque o ingestão/matching/IA é
onde o Python é mais forte (ver blueprint §7).

> **Estado:** `ingest-ean` e `feed-batch` implementados (ligam fontes reais).
> A identidade por EAN funciona **sem credenciais** (UPCitemdb trial). Icecat
> (specs) e Awin (ofertas) estão implementados mas dependem de credenciais tuas.

## Pipelines (blueprint §3)

| Pipeline | Estado | Função |
|---|---|---|
| `ingest_by_ean` | ✅ implementado | EAN → fan-out às fontes → **entity resolution** → golden record + identifiers + specs. |
| `feed_batch` | ✅ implementado | Feed Awin (CSV/gzip) → `offers`, casando por EAN. Requer `AWIN_FEED_URL`. |
| `refresh_price_live` | ⏳ stub | Google Shopping (SerpApi/Bright Data) → `offers`. Pago: só on-demand. |
| `score_recompute_month` | ⏳ stub | Recalcula `scores` + snapshots `rankings` (mês), dia 10. |
| `score_recompute_year` | ⏳ stub | Snapshots `rankings` (ano anterior). |
| `review_refresh` | ⏳ stub | Re-busca agregados de reviews (nunca o texto). |

Cada execução grava em `ingestion_runs` (auditoria + frescura visível).

## Fontes (connectors)

| Connector | Tipo | Credenciais | Estado |
|---|---|---|---|
| `upcitemdb` | identidade | nenhuma (trial) / `GO_UPC_API_KEY` | ✅ funciona ao vivo |
| `icecat` | specs | `ICECAT_USERNAME` (Open Icecat é grátis) | ✅ pronto, dá skip sem creds |
| `awin_feed` | ofertas | `AWIN_FEED_URL` | ✅ pronto, dá skip sem creds |

**Entity resolution** (`resolution.py`): EAN exato → fuzzy por marca+modelo
(`pg_trgm`) → cria golden record (marcado `needs_review` se a confiança for baixa).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # runtime + pytest
cp .env.example .env                   # DATABASE_URL, ICECAT_USERNAME, AWIN_FEED_URL, ...
```

## Correr

```bash
# Ingestão on-demand por EAN (UPCitemdb funciona sem credenciais):
python -m decifra_workers ingest-ean 049000028911            # escreve o golden record
python -m decifra_workers ingest-ean 049000028911 --dry-run  # só mostra, não escreve

# Importar feed de ofertas (requer AWIN_FEED_URL):
python -m decifra_workers feed-batch --limit 5000

# Testes (offline, sem rede/BD):
pytest -q
```

**Regra de ouro:** a IA (Claude) explica, normaliza e raciocina — **nunca** é a
fonte primária dos números. Tudo o que é facto leva `source_id` e `confidence`.
