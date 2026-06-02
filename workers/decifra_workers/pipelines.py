"""Pipelines de ingestão e recompute (blueprint §3).

`ingest_by_ean` e `feed_batch` estão implementados (ligam fontes reais). Os
restantes pipelines ficam como stubs até haver credenciais/escopo.

Regra de ouro: a IA normaliza/explica; nunca é a fonte primária dos números.
Todo o facto persistido leva source_id e confidence; cada execução grava em
`ingestion_runs` (auditoria + frescura visível ao utilizador).
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass

from . import ai, db
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

        # Enriquecimento opcional: se faltar resumo, a IA (Haiku) gera um, ancorado nos factos.
        row = conn.execute("SELECT summary FROM products WHERE id = %s", (product_id,)).fetchone()
        if row and not (row[0] or "").strip():
            summary = ai.summarize_product(best)
            if summary:
                db.update_product_summary(conn, product_id, summary)

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
        seen = matched = 0
        for ean, offer, _row in awin.stream_rows(limit=limit):
            seen += 1
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


# Critérios de ranking (cada um é só um ordenamento) → rótulo PT-PT.
CRITERIA: dict[str, str] = {
    "overall": "Melhores no geral",
    "value": "Melhor relação qualidade/preço",
    "cheapest": "Mais baratos",
    "premium": "Topo de gama",
    "material": "Melhor qualidade material",
    "feedback": "Melhores avaliações de utilizadores",
}


def _rank_for_criterion(
    products: list[dict], criterion: str
) -> list[tuple[dict, float, str]]:
    """Ordena os produtos para um critério → [(produto, score_at_time, dado_texto)]."""
    out: list[tuple[dict, float, str]] = []
    if criterion == "overall":
        cand = sorted(
            (p for p in products if p["overall"] is not None),
            key=lambda p: p["overall"],
            reverse=True,
        )
        out = [(p, p["overall"], f"DECIFRA Score {p['overall']:.0f}/100") for p in cand]
    elif criterion == "value":
        cand = [p for p in products if p["overall"] is not None and p["price"]]
        for p in cand:
            p["_vi"] = round(p["overall"] / p["price"] * 100, 1)
        cand.sort(key=lambda p: p["_vi"], reverse=True)
        out = [
            (p, p["_vi"], f"{p['_vi']:.1f} pontos de score por 100€ (score {p['overall']:.0f}, {p['price']:.0f}€)")
            for p in cand
        ]
    elif criterion == "cheapest":
        cand = sorted((p for p in products if p["price"]), key=lambda p: p["price"])
        out = [(p, p["price"], f"{p['price']:.2f}€") for p in cand]
    elif criterion == "premium":
        cand = sorted((p for p in products if p["price"]), key=lambda p: p["price"], reverse=True)
        out = [(p, p["price"], f"{p['price']:.2f}€ (topo de gama)") for p in cand]
    elif criterion == "material":
        cand = sorted(
            (p for p in products if p["material"] is not None),
            key=lambda p: p["material"],
            reverse=True,
        )
        out = [(p, p["material"], f"Qualidade material {p['material']:.0f}/100") for p in cand]
    elif criterion == "feedback":
        cand = sorted(
            (p for p in products if p["users"] is not None),
            key=lambda p: p["users"],
            reverse=True,
        )
        out = [(p, p["users"], f"Avaliações de utilizadores {p['users']:.0f}/100") for p in cand]
    return out


def score_recompute_month(
    period_key: str | None = None, settings: Settings | None = None, use_ai: bool = True
) -> RunResult:
    """Gera snapshots `rankings` (mês) para cada categoria com rankings_enabled,
    em cada critério, com o *porquê* (rationale) gerado por IA (ancorado) + fallback."""
    settings = settings or Settings.from_env()
    period_key = period_key or datetime.date.today().strftime("%Y-%m")

    def to_f(v) -> float | None:
        return float(v) if v is not None else None

    conn = db.connect(settings.database_url)
    try:
        run_id = db.start_run(conn, None, "score_recompute")
        total = 0
        for cat_id, _cat_name, _cat_slug in db.categories_with_rankings(conn):
            products = [
                {
                    "id": str(pid),
                    "name": name,
                    "brand": brand,
                    "overall": to_f(overall),
                    "material": to_f(material),
                    "users": to_f(users),
                    "price": to_f(price),
                }
                for (pid, name, brand, overall, material, users, price) in db.products_for_ranking(
                    conn, cat_id
                )
            ]
            for criterion, label in CRITERIA.items():
                top = _rank_for_criterion(products, criterion)[:5]
                if not top:
                    continue
                ranking_id = db.upsert_ranking(conn, cat_id, criterion, "month", period_key)
                for rank, (prod, score_at_time, metric_text) in enumerate(top, start=1):
                    rationale = (
                        ai.rank_rationale(prod["name"], label, metric_text, rank) if use_ai else None
                    ) or metric_text
                    db.insert_ranking_item(conn, ranking_id, rank, prod["id"], score_at_time, rationale)
                    total += 1
        db.finish_run(conn, run_id, "ok", total, f"rankings {period_key}")
        return RunResult("ok", total, notes=f"{total} itens de ranking gerados ({period_key}).")
    finally:
        conn.close()


def score_recompute_year(period_key: str) -> RunResult:
    """Cron, início de janeiro: snapshots `rankings` (ano anterior)."""
    raise NotImplementedError("Recompute anual.")


def review_refresh() -> RunResult:
    """Cron por popularidade: re-busca agregados de reviews (nunca o texto)."""
    raise NotImplementedError("Ligar fontes de review (APIs oficiais + derivados).")
