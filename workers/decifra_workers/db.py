"""Persistência (psycopg) no mesmo Postgres da app web.

Primitivas para registar fontes, registos crús (auditoria), e escrever no golden
record (products, identifiers, specs, offers) — sempre com source_id + confidence.
"""
from __future__ import annotations

from typing import Any

import psycopg
from psycopg.types.json import Jsonb

from .models import NormalizedOffer, NormalizedSpec
from .text_utils import slugify


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, autocommit=True)


def ensure_source(
    conn: psycopg.Connection, name: str, kind: str, base_url: str | None, trust_weight: float
) -> str:
    row = conn.execute(
        """
        INSERT INTO sources (name, kind, base_url, trust_weight)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (name) DO UPDATE
          SET kind = EXCLUDED.kind, base_url = EXCLUDED.base_url
        RETURNING id
        """,
        (name, kind, base_url, trust_weight),
    ).fetchone()
    return str(row[0])


def ensure_store(
    conn: psycopg.Connection, name: str, network: str | None = None, country: str | None = None
) -> str:
    found = conn.execute("SELECT id FROM stores WHERE name = %s LIMIT 1", (name,)).fetchone()
    if found:
        return str(found[0])
    row = conn.execute(
        "INSERT INTO stores (name, affiliate_network, country) VALUES (%s, %s, %s) RETURNING id",
        (name, network, country),
    ).fetchone()
    return str(row[0])


def start_run(conn: psycopg.Connection, source_id: str | None, kind: str) -> str:
    row = conn.execute(
        "INSERT INTO ingestion_runs (source_id, kind, status) VALUES (%s, %s, 'partial') RETURNING id",
        (source_id, kind),
    ).fetchone()
    return str(row[0])


def finish_run(
    conn: psycopg.Connection, run_id: str, status: str, items: int, notes: str = ""
) -> None:
    conn.execute(
        "UPDATE ingestion_runs SET status=%s, items=%s, notes=%s, finished_at=now() WHERE id=%s",
        (status, items, notes, run_id),
    )


def record_source_record(
    conn: psycopg.Connection,
    source_id: str,
    raw_payload: dict[str, Any] | None,
    ean_seen: str | None,
    name_seen: str | None,
    product_id: str | None = None,
) -> str:
    row = conn.execute(
        """
        INSERT INTO source_records (source_id, product_id, raw_payload, ean_seen, name_seen)
        VALUES (%s, %s, %s, %s, %s) RETURNING id
        """,
        (source_id, product_id, Jsonb(raw_payload) if raw_payload is not None else None, ean_seen, name_seen),
    ).fetchone()
    return str(row[0])


def find_product_by_ean(conn: psycopg.Connection, ean: str) -> str | None:
    row = conn.execute(
        "SELECT product_id FROM product_identifiers WHERE id_type='ean' AND id_value=%s LIMIT 1",
        (ean,),
    ).fetchone()
    return str(row[0]) if row else None


def fuzzy_match_product(conn: psycopg.Connection, name: str, threshold: float) -> tuple[str, float] | None:
    """Melhor candidato por similaridade trigram em marca+modelo (pg_trgm)."""
    if not name.strip():
        return None
    row = conn.execute(
        """
        SELECT id, similarity(coalesce(brand,'') || ' ' || coalesce(model,''), %s) AS sim
        FROM products
        WHERE (coalesce(brand,'') || ' ' || coalesce(model,'')) %% %s
        ORDER BY sim DESC
        LIMIT 1
        """,
        (name, name),
    ).fetchone()
    if row and row[1] is not None and float(row[1]) >= threshold:
        return str(row[0]), float(row[1])
    return None


def _unique_slug(conn: psycopg.Connection, base: str) -> str:
    slug, i = base, 2
    while conn.execute("SELECT 1 FROM products WHERE slug=%s", (slug,)).fetchone():
        slug = f"{base}-{i}"
        i += 1
    return slug


def create_product(
    conn: psycopg.Connection,
    *,
    brand: str | None,
    model: str | None,
    name: str | None,
    summary: str | None,
    image_url: str | None,
    match_confidence: float,
    needs_review: bool,
) -> str:
    slug = _unique_slug(conn, slugify(brand, model) if (brand or model) else slugify(name))
    canonical = name or " ".join(filter(None, [brand, model])) or slug
    row = conn.execute(
        """
        INSERT INTO products (slug, brand, model, canonical_name, summary, image_url,
                              status, match_confidence, needs_review)
        VALUES (%s, %s, %s, %s, %s, %s, 'a_venda', %s, %s)
        RETURNING id
        """,
        (slug, brand, model, canonical, summary, image_url, match_confidence, needs_review),
    ).fetchone()
    return str(row[0])


def update_product_summary(conn: psycopg.Connection, product_id: str, summary: str) -> None:
    conn.execute("UPDATE products SET summary = %s WHERE id = %s", (summary, product_id))


def upsert_identifier(conn: psycopg.Connection, product_id: str, id_type: str, id_value: str) -> None:
    conn.execute(
        """
        INSERT INTO product_identifiers (product_id, id_type, id_value)
        VALUES (%s, %s, %s)
        ON CONFLICT (id_type, id_value) DO NOTHING
        """,
        (product_id, id_type, id_value),
    )


def upsert_spec(conn: psycopg.Connection, product_id: str, source_id: str, spec: NormalizedSpec) -> None:
    # Idempotente por (produto, atributo, fonte): substitui o valor dessa fonte.
    conn.execute(
        "DELETE FROM specs WHERE product_id=%s AND attribute_key=%s AND source_id=%s",
        (product_id, spec.key, source_id),
    )
    conn.execute(
        """
        INSERT INTO specs (product_id, attribute_key, value_text, value_num, unit, source_id, confidence)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (product_id, spec.key, spec.value_text, spec.value_num, spec.unit, source_id, spec.confidence),
    )


def upsert_offer(
    conn: psycopg.Connection, product_id: str, store_id: str, source_id: str, offer: NormalizedOffer
) -> None:
    conn.execute(
        "DELETE FROM offers WHERE product_id=%s AND store_id=%s AND source_id=%s",
        (product_id, store_id, source_id),
    )
    conn.execute(
        """
        INSERT INTO offers (product_id, store_id, price, currency, url_affiliate, in_stock, source_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (product_id, store_id, offer.price, offer.currency, offer.url_affiliate, offer.in_stock, source_id),
    )


# ── Rankings (snapshots por período) ─────────────────────────────────────────
def categories_with_rankings(conn: psycopg.Connection) -> list[tuple[str, str, str]]:
    rows = conn.execute(
        "SELECT id, name, slug FROM categories WHERE rankings_enabled = true ORDER BY name"
    ).fetchall()
    return [(str(r[0]), r[1], r[2]) for r in rows]


def products_for_ranking(conn: psycopg.Connection, category_id: str) -> list[tuple]:
    """Produtos da categoria com score e preço mais baixo em stock."""
    return conn.execute(
        """
        SELECT p.id, p.canonical_name, p.brand,
               s.overall, s.sub_material, s.sub_users,
               (SELECT min(price) FROM offers o WHERE o.product_id = p.id AND o.in_stock = true) AS price,
               p.slug
        FROM products p
        LEFT JOIN scores s ON s.product_id = p.id
        WHERE p.category_id = %s
        """,
        (category_id,),
    ).fetchall()


def slugs_for(conn: psycopg.Connection, product_ids: list[str]) -> list[str]:
    if not product_ids:
        return []
    rows = conn.execute(
        "SELECT slug FROM products WHERE id = ANY(%s)", (product_ids,)
    ).fetchall()
    return [r[0] for r in rows]


def upsert_ranking(
    conn: psycopg.Connection, category_id: str, criterion: str, period_type: str, period_key: str
) -> str:
    """Cria/recria o snapshot (limpa itens antigos do mesmo período — recompute)."""
    existing = conn.execute(
        "SELECT id FROM rankings WHERE category_id=%s AND criterion=%s AND period_type=%s AND period_key=%s",
        (category_id, criterion, period_type, period_key),
    ).fetchone()
    if existing:
        rid = str(existing[0])
        conn.execute("DELETE FROM ranking_items WHERE ranking_id = %s", (rid,))
        conn.execute("UPDATE rankings SET generated_at = now() WHERE id = %s", (rid,))
        return rid
    row = conn.execute(
        """
        INSERT INTO rankings (category_id, criterion, period_type, period_key)
        VALUES (%s, %s, %s, %s) RETURNING id
        """,
        (category_id, criterion, period_type, period_key),
    ).fetchone()
    return str(row[0])


def insert_ranking_item(
    conn: psycopg.Connection,
    ranking_id: str,
    rank: int,
    product_id: str,
    score_at_time: float,
    rationale: str,
) -> None:
    conn.execute(
        """
        INSERT INTO ranking_items (ranking_id, rank, product_id, score_at_time, rationale)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (ranking_id, rank, product_id, score_at_time, rationale),
    )


# ── Finder (cauda longa: escolha de atributos discriminantes por IA) ─────────
def category_by_slug(conn: psycopg.Connection, slug: str) -> tuple[str, str, str] | None:
    row = conn.execute("SELECT id, name, slug FROM categories WHERE slug = %s", (slug,)).fetchone()
    return (str(row[0]), row[1], row[2]) if row else None


def categories_needing_questions(conn: psycopg.Connection) -> list[tuple[str, str, str]]:
    """Categorias com atributos mas sem nenhum discriminante (a cauda longa)."""
    rows = conn.execute(
        """
        SELECT c.id, c.name, c.slug FROM categories c
        WHERE EXISTS (SELECT 1 FROM category_attributes a WHERE a.category_id = c.id)
          AND NOT EXISTS (
            SELECT 1 FROM category_attributes a
            WHERE a.category_id = c.id AND a.is_discriminant = true
          )
        ORDER BY c.name
        """
    ).fetchall()
    return [(str(r[0]), r[1], r[2]) for r in rows]


def attribute_stats(conn: psycopg.Connection, category_id: str) -> list[dict]:
    """Para cada atributo da categoria, os valores distintos presentes nos produtos."""
    attrs = conn.execute(
        "SELECT key, label, data_type, unit FROM category_attributes WHERE category_id = %s ORDER BY display_order",
        (category_id,),
    ).fetchall()
    stats = []
    for key, label, data_type, unit in attrs:
        vals = conn.execute(
            """
            SELECT DISTINCT coalesce(s.value_text, s.value_num::text) AS v
            FROM specs s JOIN products p ON p.id = s.product_id
            WHERE p.category_id = %s AND s.attribute_key = %s
              AND (s.value_text IS NOT NULL OR s.value_num IS NOT NULL)
            ORDER BY v
            """,
            (category_id, key),
        ).fetchall()
        stats.append(
            {
                "key": key,
                "label": label,
                "data_type": data_type,
                "unit": unit,
                "values": [r[0] for r in vals],
            }
        )
    return stats


def set_discriminant(conn: psycopg.Connection, category_id: str, keys: list[str]) -> None:
    conn.execute(
        "UPDATE category_attributes SET is_discriminant = false WHERE category_id = %s",
        (category_id,),
    )
    if keys:
        conn.execute(
            "UPDATE category_attributes SET is_discriminant = true WHERE category_id = %s AND key = ANY(%s)",
            (category_id, keys),
        )


# ── DECIFRA Score: recompute a partir de sinais reais ────────────────────────
def source_id_by_name(conn: psycopg.Connection, name: str) -> str | None:
    row = conn.execute("SELECT id FROM sources WHERE name = %s", (name,)).fetchone()
    return str(row[0]) if row else None


def products_in_category(conn: psycopg.Connection, category_id: str) -> list[tuple[str, str, str]]:
    rows = conn.execute(
        "SELECT id, slug, canonical_name FROM products WHERE category_id = %s", (category_id,)
    ).fetchall()
    return [(str(r[0]), r[1], r[2]) for r in rows]


def scoring_inputs(conn: psycopg.Connection, product_id: str) -> dict:
    """Reúne os sinais reais de um produto para o cálculo dos sub-scores."""

    def f(v):
        return float(v) if v is not None else None

    expert = conn.execute(
        """
        SELECT s.normalized, coalesce(src.trust_weight, 0.5)
        FROM score_signals s LEFT JOIN sources src ON src.id = s.source_id
        WHERE s.product_id = %s AND s.signal_type = 'expert_review' AND s.normalized IS NOT NULL
        """,
        (product_id,),
    ).fetchall()
    reviews = conn.execute(
        """
        SELECT r.rating_adjusted, r.review_count, r.source_id, coalesce(src.trust_weight, 0.5)
        FROM reviews_aggregate r LEFT JOIN sources src ON src.id = r.source_id
        WHERE r.product_id = %s
        """,
        (product_id,),
    ).fetchall()
    specs = conn.execute(
        "SELECT attribute_key, value_num, value_text, source_id FROM specs WHERE product_id = %s",
        (product_id,),
    ).fetchall()
    themes = conn.execute(
        "SELECT theme, polarity, frequency FROM review_themes WHERE product_id = %s", (product_id,)
    ).fetchall()
    price = conn.execute(
        "SELECT min(price) FROM offers WHERE product_id = %s AND in_stock = true", (product_id,)
    ).fetchone()[0]
    trusts = conn.execute(
        """
        SELECT coalesce(trust_weight, 0.5) FROM sources WHERE id IN (
            SELECT source_id FROM score_signals WHERE product_id = %s AND source_id IS NOT NULL
            UNION SELECT source_id FROM reviews_aggregate WHERE product_id = %s AND source_id IS NOT NULL
            UNION SELECT source_id FROM specs WHERE product_id = %s AND source_id IS NOT NULL
        )
        """,
        (product_id, product_id, product_id),
    ).fetchall()
    return {
        "expert": [(f(n), float(t)) for n, t in expert],
        "reviews": [(f(r), int(c), str(sid) if sid else None, float(t)) for r, c, sid, t in reviews],
        "specs": [(k, f(vn), vt, str(sid) if sid else None) for k, vn, vt, sid in specs],
        "themes": [(th, pol, int(fr)) for th, pol, fr in themes],
        "price": f(price),
        "trusts": [float(t) for (t,) in trusts],
    }


def upsert_score(
    conn: psycopg.Connection,
    product_id: str,
    overall: float | None,
    sub_expert: float | None,
    sub_users: float | None,
    sub_material: float | None,
    sub_value: float | None,
    confidence: float | None,
) -> None:
    conn.execute(
        """
        INSERT INTO scores (product_id, overall, sub_expert, sub_users, sub_material, sub_value, confidence, computed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (product_id) DO UPDATE SET
            overall = EXCLUDED.overall, sub_expert = EXCLUDED.sub_expert, sub_users = EXCLUDED.sub_users,
            sub_material = EXCLUDED.sub_material, sub_value = EXCLUDED.sub_value,
            confidence = EXCLUDED.confidence, computed_at = now()
        """,
        (product_id, overall, sub_expert, sub_users, sub_material, sub_value, confidence),
    )


_DERIVED_SIGNALS = ("user_rating", "material", "warranty", "durability", "certification", "value")


def replace_derived_signals(conn: psycopg.Connection, product_id: str, signals: list[dict]) -> None:
    """Substitui os sinais DERIVADOS (mantém os curados, ex.: expert_review)."""
    conn.execute(
        "DELETE FROM score_signals WHERE product_id = %s AND signal_type = ANY(%s)",
        (product_id, list(_DERIVED_SIGNALS)),
    )
    for s in signals:
        conn.execute(
            """
            INSERT INTO score_signals
                (product_id, signal_type, raw_value, normalized, weight, source_id, source_url, confidence)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                product_id,
                s["signal_type"],
                s.get("raw_value"),
                s.get("normalized"),
                s.get("weight"),
                s.get("source_id"),
                s.get("source_url"),
                s.get("confidence"),
            ),
        )


def categories_for_scoring(conn: psycopg.Connection) -> list[tuple[str, str, bool]]:
    """Categorias com produtos (id, slug, rankings_enabled)."""
    rows = conn.execute(
        """
        SELECT id, slug, rankings_enabled FROM categories c
        WHERE EXISTS (SELECT 1 FROM products p WHERE p.category_id = c.id)
        ORDER BY slug
        """
    ).fetchall()
    return [(str(r[0]), r[1], bool(r[2])) for r in rows]


def ranking_exists(
    conn: psycopg.Connection, category_id: str, criterion: str, period_type: str, period_key: str
) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM rankings WHERE category_id=%s AND criterion=%s AND period_type=%s AND period_key=%s",
            (category_id, criterion, period_type, period_key),
        ).fetchone()
        is not None
    )


# ── Reviews (só métricas derivadas — NUNCA texto) ────────────────────────────
def product_by_slug(conn: psycopg.Connection, slug: str) -> tuple[str, str] | None:
    row = conn.execute(
        "SELECT id, canonical_name FROM products WHERE slug = %s", (slug,)
    ).fetchone()
    return (str(row[0]), row[1]) if row else None


def upsert_reviews_aggregate(
    conn: psycopg.Connection,
    product_id: str,
    source_id: str,
    *,
    rating_raw: float | None,
    rating_adjusted: float | None,
    review_count: int,
    distribution: dict | None,
    authenticity_score: float | None,
    sentiment_summary: str | None,
    source_url: str | None,
) -> None:
    """Grava SÓ métricas + resumo próprio + link. Sem texto de reviews (§5)."""
    conn.execute(
        """
        INSERT INTO reviews_aggregate
            (product_id, source_id, rating_raw, rating_adjusted, review_count, distribution,
             authenticity_score, sentiment_summary, source_url, fetched_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
        ON CONFLICT (product_id, source_id) DO UPDATE SET
            rating_raw = EXCLUDED.rating_raw, rating_adjusted = EXCLUDED.rating_adjusted,
            review_count = EXCLUDED.review_count, distribution = EXCLUDED.distribution,
            authenticity_score = EXCLUDED.authenticity_score,
            sentiment_summary = EXCLUDED.sentiment_summary, source_url = EXCLUDED.source_url,
            fetched_at = now()
        """,
        (
            product_id,
            source_id,
            rating_raw,
            rating_adjusted,
            review_count,
            Jsonb(distribution) if distribution is not None else None,
            authenticity_score,
            sentiment_summary,
            source_url,
        ),
    )


def replace_review_themes(conn: psycopg.Connection, product_id: str, themes: list[dict]) -> None:
    conn.execute("DELETE FROM review_themes WHERE product_id = %s", (product_id,))
    for t in themes:
        conn.execute(
            "INSERT INTO review_themes (product_id, theme, polarity, frequency) VALUES (%s, %s, %s, %s)",
            (product_id, t["theme"], t.get("polarity", "misto"), int(t.get("frequency") or 1)),
        )
