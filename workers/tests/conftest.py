"""Fixtures de BD para os testes de entity resolution contra Postgres.

Isolamento NÃO-destrutivo: cada teste corre num schema temporário próprio
(`decifra_test_tmp`), criado e largado na fixture — nunca toca nas tabelas reais
(`public`) nem nos seus dados. Skip limpo se `DATABASE_URL` não estiver acessível
ou faltar `pg_trgm` (mantém o job unitário do CI, sem BD, a passar).

Os testes que usam `db_conn` são marcados automaticamente como `integration`, pelo
que correm no job e2e do CI (`pytest -m integration`, que migra a BD) e ficam
fora do `pytest` por defeito (`addopts = -m "not integration"`) — sem erro.
"""
from __future__ import annotations

import os

import pytest

_SCHEMA = "decifra_test_tmp"

# Subconjunto do schema real (web/drizzle/0000_init.sql) tocado por
# create_product / fuzzy_match_product / flag_needs_review / upsert_identifier.
# Criado dentro do schema temporário (search_path), nunca em `public`.
_PRODUCTS_DDL = """
CREATE TABLE products (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug             varchar(200) NOT NULL UNIQUE,
  brand            varchar(160),
  model            varchar(200),
  canonical_name   varchar(300),
  summary          text,
  image_url        varchar(800),
  status           varchar(24) NOT NULL DEFAULT 'a_venda',
  match_confidence numeric,
  needs_review     boolean NOT NULL DEFAULT false,
  created_at       timestamptz NOT NULL DEFAULT now(),
  updated_at       timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE product_identifiers (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  product_id  uuid NOT NULL REFERENCES products (id) ON DELETE CASCADE,
  id_type     varchar(24) NOT NULL,
  id_value    varchar(120) NOT NULL,
  UNIQUE (id_type, id_value)
);
"""


def pytest_collection_modifyitems(config, items):
    """Testes que tocam a BD (fixture `db_conn`) correm como `integration`."""
    for item in items:
        if "db_conn" in getattr(item, "fixturenames", ()):
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def _db_url() -> str:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL ausente — skip dos testes de resolution com BD.")
    try:
        import psycopg

        with psycopg.connect(url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DATABASE_URL inacessível ({exc}) — skip dos testes de resolution.")
    return url


@pytest.fixture()
def db_conn(_db_url):
    import psycopg

    conn = psycopg.connect(_db_url, autocommit=True)
    # pg_trgm vem da migração real; não a criamos (evita exigir superuser).
    if not conn.execute("SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm'").fetchone():
        conn.close()
        pytest.skip("pg_trgm ausente — corre `npm run db:migrate` antes destes testes.")
    # Isolamento não-destrutivo: schema temporário próprio (nunca toca em `public`).
    conn.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE")
    conn.execute(f"CREATE SCHEMA {_SCHEMA}")
    conn.execute(f"SET search_path TO {_SCHEMA}, public")
    for stmt in filter(str.strip, _PRODUCTS_DDL.split(";")):
        conn.execute(stmt)
    try:
        yield conn
    finally:
        conn.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE")
        conn.close()
