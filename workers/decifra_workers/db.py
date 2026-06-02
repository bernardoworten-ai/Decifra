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
