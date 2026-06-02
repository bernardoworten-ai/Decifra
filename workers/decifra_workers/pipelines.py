"""Pipelines de ingestão e recompute (blueprint §3).

`ingest_by_ean` e `feed_batch` estão implementados (ligam fontes reais). Os
restantes pipelines ficam como stubs até haver credenciais/escopo.

Regra de ouro: a IA normaliza/explica; nunca é a fonte primária dos números.
Todo o facto persistido leva source_id e confidence; cada execução grava em
`ingestion_runs` (auditoria + frescura visível ao utilizador).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import db
from .config import Settings
from .resolution import resolve_product
from .sources import build_connectors
from .sources.awin import AwinFeedConnector


@dataclass
class RunResult:
    status: str  # "ok" | "partial" | "error"
    items: int
    notes: str = ""
    product_id: str | None = None


def ingest_by_ean(ean: str, settings: Settings | None = None, dry_run: bool = False) -> RunResult:
    """On-demand: fan-out às fontes de identidade/specs configuradas → entity
    resolution → golden record (products) + identifiers + specs."""
    settings = settings or Settings.from_env()
    connectors = [c for c in build_connectors(settings) if c.kind in ("identity", "specs")]

    # 1. Fan-out: recolher RawRecords das fontes configuradas.
    records = [(c, rec) for c in connectors if c.configured() if (rec := c.fetch_by_ean(ean))]
    if not records:
        names = [c.name for c in connectors if c.configured()]
        return RunResult("error", 0, notes=f"Sem resultados para EAN {ean} (fontes: {names}).")

    # Melhor identidade = maior confiança de merge (identidade ou specs com marca).
    best = max((rec for _, rec in records), key=lambda r: r.match_confidence)

    if dry_run:
        specs = sum(len(rec.specs) for _, rec in records)
        srcs = ", ".join(c.name for c, _ in records)
        return RunResult(
            "ok", len(records),
            notes=f"[dry-run] '{best.name}' marca={best.brand} modelo={best.model} "
                  f"· {specs} specs · fontes: {srcs}",
        )

    conn = db.connect(settings.database_url)
    try:
        resolution = resolve_product(conn, best)
        product_id = resolution.product_id
        spec_items = 0
        for connector, rec in records:
            source_id = db.ensure_source(
                conn, connector.name, connector.kind, connector.base_url, connector.trust_weight
            )
            run_id = db.start_run(conn, source_id, "on_demand")
            db.record_source_record(conn, source_id, rec.raw_payload, rec.ean, rec.name, product_id)
            if rec.ean:
                db.upsert_identifier(conn, product_id, "ean", rec.ean)
            for spec in rec.specs:
                db.upsert_spec(conn, product_id, source_id, spec)
                spec_items += 1
            db.finish_run(conn, run_id, "ok", len(rec.specs), f"{connector.name} → {product_id}")

        state = "novo" if resolution.created else "existente"
        return RunResult(
            "ok", spec_items, product_id=product_id,
            notes=f"match={resolution.method} · produto {product_id} ({state}) · {spec_items} specs",
        )
    finally:
        conn.close()


def feed_batch(settings: Settings | None = None, limit: int | None = None) -> RunResult:
    """Cron diário: importa o feed Awin (preço, deep link) → `offers`, casando por
    EAN com o golden record existente (o feed traz milhares; só casamos o que temos)."""
    settings = settings or Settings.from_env()
    awin = AwinFeedConnector(feed_url=settings.awin_feed_url)
    if not awin.configured():
        return RunResult("error", 0, notes="AWIN_FEED_URL não configurado — feed_batch ignorado.")

    conn = db.connect(settings.database_url)
    try:
        source_id = db.ensure_source(conn, awin.name, awin.kind, awin.base_url, awin.trust_weight)
        run_id = db.start_run(conn, source_id, "feed_batch")
        text = awin.download()
        seen = matched = 0
        for ean, offer, _row in awin.parse_rows(text):
            seen += 1
            if limit and seen > limit:
                break
            if not ean:
                continue
            product_id = db.find_product_by_ean(conn, ean)
            if not product_id:
                continue
            store_id = db.ensure_store(conn, offer.store_name, network="awin")
            db.upsert_offer(conn, product_id, store_id, source_id, offer)
            matched += 1
        db.finish_run(conn, run_id, "ok", matched, f"{seen} linhas, {matched} ofertas casadas.")
        return RunResult("ok", matched, notes=f"{seen} linhas processadas, {matched} ofertas atualizadas.")
    finally:
        conn.close()


# ── Ainda por implementar (próximas fases) ────────────────────────────────────
def refresh_price_live(product_id: str) -> RunResult:
    """Botão "atualizar": Google Shopping (SerpApi/Bright Data) → `offers`. Pago."""
    raise NotImplementedError("Ligar SerpApi/Bright Data.")


def score_recompute_month(period_key: str) -> RunResult:
    """Cron, dia 10: recalcula `scores` + snapshots `rankings` (mês)."""
    raise NotImplementedError("Recompute mensal + snapshots de ranking.")


def score_recompute_year(period_key: str) -> RunResult:
    """Cron, início de janeiro: snapshots `rankings` (ano anterior)."""
    raise NotImplementedError("Recompute anual.")


def review_refresh() -> RunResult:
    """Cron por popularidade: re-busca agregados de reviews (nunca o texto)."""
    raise NotImplementedError("Ligar fontes de review (APIs oficiais + derivados).")
