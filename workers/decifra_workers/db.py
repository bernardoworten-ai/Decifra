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
