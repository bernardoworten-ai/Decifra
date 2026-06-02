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

from . import ai, cache, db, scoring
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
        touched: set[str] = set()
        for ean, offer, _row in awin.stream_rows(limit=limit):
            seen += 1
            if not ean:
                continue
            product_id = db.find_product_by_ean(conn, ean)
            if not product_id:
                continue
            store_id = db.ensure_store(conn, offer.store_name, network="awin")
            db.upsert_offer(conn, product_id, store_id, source_id, offer)
            touched.add(product_id)
            matched += 1
        # Invalida a cache dos produtos cujas ofertas mudaram (preço fresco no lookup).
        for slug in db.slugs_for(conn, list(touched)):
            cache.invalidate_product(slug)
        db.finish_run(conn, run_id, "ok", matched, f"{seen} linhas, {matched} ofertas casadas.")
        return RunResult("ok", matched, notes=f"{seen} linhas processadas, {matched} ofertas atualizadas.")
    finally:
        conn.close()


def generate_finder_questions(
    category_slug: str | None = None, settings: Settings | None = None, use_ai: bool = True
) -> RunResult:
    """Cauda longa: para categorias sem perguntas curadas, o Haiku escolhe os
    atributos discriminantes (validado por variância; fallback determinístico)."""
    settings = settings or Settings.from_env()
    conn = db.connect(settings.database_url)
    try:
        run_id = db.start_run(conn, None, "finder_questions")
        if category_slug:
            target = db.category_by_slug(conn, category_slug)
            targets = [target] if target else []
        else:
            targets = db.categories_needing_questions(conn)

        total = 0
        details: list[str] = []
        for cat_id, cat_name, slug in targets:
            stats = db.attribute_stats(conn, cat_id)
            varying = [s for s in stats if len(s["values"]) > 1]
            chosen = ai.choose_discriminant_attributes(cat_name, stats) if use_ai else []
            varying_keys = {s["key"] for s in varying}
            valid = [k for k in chosen if k in varying_keys][:5]
            if not valid:  # fallback: por variância (mais valores distintos primeiro)
                valid = [s["key"] for s in sorted(varying, key=lambda s: len(s["values"]), reverse=True)][:5]
            db.set_discriminant(conn, cat_id, valid)
            total += len(valid)
            details.append(f"{slug}: {valid}")

        notes = "; ".join(details) or "nada a fazer"
        db.finish_run(conn, run_id, "ok", total, notes)
        return RunResult("ok", total, notes=notes)
    finally:
        conn.close()


def check_price_alerts(settings: Settings | None = None) -> RunResult:
    """Verifica os favoritos com alerta: dispara quando o preço mais baixo em
    stock desce ao/abaixo do alvo. (Envio por email pendente do fornecedor.)"""
    settings = settings or Settings.from_env()
    conn = db.connect(settings.database_url)
    try:
        run_id = db.start_run(conn, None, "price_alert")
        rows = conn.execute(
            """
            SELECT u.email, p.canonical_name, si.price_alert,
                   (SELECT min(price) FROM offers o WHERE o.product_id = si.product_id AND o.in_stock = true) AS cheapest
            FROM saved_items si
            JOIN products p ON p.id = si.product_id
            JOIN users u ON u.id = si.user_id
            WHERE si.price_alert IS NOT NULL
            """
        ).fetchall()

        triggered = 0
        for email, name, alert, cheapest in rows:
            if cheapest is not None and float(cheapest) <= float(alert):
                triggered += 1
                dest = email or "(utilizador anónimo, sem email)"
                print(f"[alerta] {name}: {float(cheapest):.2f}€ ≤ {float(alert):.2f}€ → {dest}")

        db.finish_run(conn, run_id, "ok", triggered, f"{len(rows)} alertas, {triggered} disparados")
        return RunResult(
            "ok", triggered,
            notes=f"{triggered}/{len(rows)} alertas disparados (envio de email pendente).",
        )
    finally:
        conn.close()


def consolidate(eans: list[str], settings: Settings | None = None, use_ai: bool = True) -> RunResult:
    """Consolidação real, num só comando: para cada EAN faz ingest_by_ean
    (identidade UPCitemdb + specs Icecat quando disponível + resumo IA) e, no fim,
    recalcula rankings e (re)escolhe perguntas do finder. Degrada graciosamente:
    sem Icecat traz só identidade; ganha specs assim que o app_key abrir."""
    settings = settings or Settings.from_env()
    ok = 0
    details: list[str] = []
    for ean in eans:
        res = ingest_by_ean(ean, settings=settings)
        details.append(f"{ean}={res.status}")
        if res.status == "ok":
            ok += 1
    # Pós-processamento (best-effort; não quebra a consolidação).
    try:
        score_recompute_month(settings=settings, use_ai=use_ai)
    except Exception as exc:  # noqa: BLE001
        details.append(f"recompute_falhou:{exc}")
    try:
        generate_finder_questions(settings=settings, use_ai=use_ai)
    except Exception as exc:  # noqa: BLE001
        details.append(f"finder_falhou:{exc}")
    status = "ok" if ok == len(eans) and eans else ("partial" if ok else "error")
    return RunResult(status, ok, notes=f"{ok}/{len(eans)} ingeridos · " + "; ".join(details))


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


def _is_closed(period_type: str, period_key: str) -> bool:
    """Período já fechado (passado) ⇒ snapshot imutável (§10)."""
    today = datetime.date.today()
    if period_type == "month":
        return period_key < today.strftime("%Y-%m")
    if period_type == "year":
        return period_key < str(today.year)
    return False


def _spec_num(specs: list, key: str) -> float | None:
    for k, vnum, _vtext, _sid in specs:
        if k == key and vnum is not None:
            return vnum
    return None


_CERT_TOKENS = ("ip5", "ip6", "ip67", "ip68", "ipx", "mil-std", "mil std")


def _has_certification(specs: list) -> bool:
    return any(
        vtext and any(tok in vtext.lower() for tok in _CERT_TOKENS) for _k, _vn, vtext, _sid in specs
    )


_DURABILITY_WORDS = ("constru", "fiabil", "durab", "build", "robust", "material")


def _durability_theme_freqs(themes: list) -> tuple[int, int]:
    pos = neg = 0
    for theme, polarity, freq in themes:
        if any(w in theme.lower() for w in _DURABILITY_WORDS):
            if polarity == "positivo":
                pos += freq
            elif polarity == "negativo":
                neg += freq
    return pos, neg


def _derived_signals(c: dict, sub_value: float | None, weights: dict, icecat_src: str | None) -> list[dict]:
    """Sinais derivados auditáveis (source/confidence). Os curados (expert_review) não se tocam."""
    sigs: list[dict] = []
    if c["users"] is not None:
        sigs.append({"signal_type": "user_rating", "raw_value": round(c["users"] / 20, 2),
                     "normalized": c["users"], "weight": weights["users"], "source_id": c["user_src"], "confidence": 0.7})
    if c["warranty"] is not None:
        sigs.append({"signal_type": "warranty", "raw_value": c["warranty"], "source_id": icecat_src, "confidence": 0.8})
    if c["theme_pos"] or c["theme_neg"]:
        sigs.append({"signal_type": "durability", "raw_value": c["theme_pos"] - c["theme_neg"], "confidence": 0.6})
    if c["has_cert"]:
        sigs.append({"signal_type": "certification", "raw_value": 1, "source_id": icecat_src, "confidence": 0.8})
    if c["material"] is not None:
        sigs.append({"signal_type": "material", "normalized": c["material"], "weight": weights["material"],
                     "source_id": icecat_src, "confidence": 0.7})
    if sub_value is not None:
        sigs.append({"signal_type": "value", "raw_value": c["price"], "normalized": sub_value,
                     "weight": weights["value"], "confidence": 0.6})
    return sigs


def score_recompute(
    period: str = "month",
    period_key: str | None = None,
    settings: Settings | None = None,
    use_ai: bool = True,
) -> RunResult:
    """Recalcula os scores a partir de SINAIS reais (renormalizando os ausentes) e
    CONGELA snapshots de ranking por critério nas categorias com rankings_enabled
    (§3/§4). period: 'month' (dia 10) | 'year' (início de janeiro). Snapshots de
    períodos já fechados são imutáveis (§10)."""
    settings = settings or Settings.from_env()
    today = datetime.date.today()
    period_type = "year" if period == "year" else "month"
    period_key = period_key or (str(today.year) if period_type == "year" else today.strftime("%Y-%m"))

    conn = db.connect(settings.database_url)
    try:
        run_id = db.start_run(conn, None, "score_recompute")
        scored = snapshots = 0
        touched_slugs: set[str] = set()
        icecat_src = db.source_id_by_name(conn, "icecat")

        for cat_id, cat_slug, rankings_enabled in db.categories_for_scoring(conn):
            weights = scoring.weights_for(cat_slug)
            computed: list[dict] = []

            for pid, pslug, pname in db.products_in_category(conn, cat_id):
                ins = db.scoring_inputs(conn, pid)
                sub_expert = scoring.aggregate_expert(ins["expert"])
                sub_users = scoring.aggregate_users([(r, c) for r, c, _sid, _t in ins["reviews"]])
                warranty = _spec_num(ins["specs"], "garantia")
                tbw = _spec_num(ins["specs"], "tbw")
                has_cert = _has_certification(ins["specs"])
                pos, neg = _durability_theme_freqs(ins["themes"])
                sub_material = scoring.material_score(warranty, tbw, has_cert, pos, neg)
                base_quality = scoring.combine_overall(
                    {"expert": sub_expert, "users": sub_users, "material": sub_material}, weights
                )
                user_src = next((sid for _r, _c, sid, _t in ins["reviews"] if sid), None)
                computed.append({
                    "id": pid, "slug": pslug, "name": pname, "price": ins["price"],
                    "expert": sub_expert, "users": sub_users, "material": sub_material,
                    "base_quality": base_quality, "trusts": ins["trusts"], "warranty": warranty,
                    "tbw": tbw, "has_cert": has_cert, "theme_pos": pos, "theme_neg": neg, "user_src": user_src,
                })

            values = scoring.value_scores([(c["id"], c["base_quality"], c["price"]) for c in computed])
            ranked: list[dict] = []
            for c in computed:
                sub_value = values.get(c["id"])
                subs = {"expert": c["expert"], "users": c["users"], "material": c["material"], "value": sub_value}
                overall = scoring.combine_overall(subs, weights)
                avg_trust = sum(c["trusts"]) / len(c["trusts"]) if c["trusts"] else 0.0
                confidence = scoring.confidence_from_sources(len(c["trusts"]), avg_trust)
                db.upsert_score(conn, c["id"], overall, c["expert"], c["users"], c["material"], sub_value, confidence)
                db.replace_derived_signals(conn, c["id"], _derived_signals(c, sub_value, weights, icecat_src))
                scored += 1
                ranked.append({**c, "overall": overall})

            if rankings_enabled:
                for criterion, label in CRITERIA.items():
                    if _is_closed(period_type, period_key) and db.ranking_exists(
                        conn, cat_id, criterion, period_type, period_key
                    ):
                        continue  # snapshot de período fechado → imutável
                    top = _rank_for_criterion(ranked, criterion)[:5]
                    if not top:
                        continue
                    ranking_id = db.upsert_ranking(conn, cat_id, criterion, period_type, period_key)
                    for rank, (prod, score_at_time, metric_text) in enumerate(top, start=1):
                        rationale = (
                            ai.rank_rationale(prod["name"], label, metric_text, rank) if use_ai else None
                        ) or metric_text
                        db.insert_ranking_item(conn, ranking_id, rank, prod["id"], score_at_time, rationale)
                        touched_slugs.add(prod["slug"])
                    snapshots += 1

        for slug in touched_slugs:
            cache.invalidate_product(slug)
        notes = f"{period_type} {period_key}: {scored} scores, {snapshots} snapshots"
        db.finish_run(conn, run_id, "ok", scored, notes)
        return RunResult("ok", scored, notes=notes)
    finally:
        conn.close()


def score_recompute_month(
    period_key: str | None = None, settings: Settings | None = None, use_ai: bool = True
) -> RunResult:
    """Compat: recompute mensal (chama score_recompute('month'))."""
    return score_recompute("month", period_key, settings, use_ai)


def score_recompute_year(period_key: str) -> RunResult:
    """Cron, início de janeiro: snapshots `rankings` (ano anterior)."""
    raise NotImplementedError("Recompute anual.")


def review_refresh() -> RunResult:
    """Cron por popularidade: re-busca agregados de reviews (nunca o texto)."""
    raise NotImplementedError("Ligar fontes de review (APIs oficiais + derivados).")
