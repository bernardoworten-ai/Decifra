"""Teste de integração e2e: ciclo completo de ingestão contra o Postgres.

Marcado @pytest.mark.integration. Faz skip limpo se a BD não estiver acessível,
para a CI (sem BD) não partir. Corre ingest_by_ean em modo real para um EAN que
resolve ao vivo e verifica que ficam gravados golden record + specs +
≥1 source_record + um ingestion_run.

EAN: 4948570114344 — iiyama ProLite X4071UHSU-B1 (resolve no Open Icecat, ~86
specs, e na UPCitemdb). Requer rede + DATABASE_URL acessível.
"""
from __future__ import annotations

import os

import pytest

EAN = "4948570114344"


def _can_connect(url: str) -> bool:
    try:
        import psycopg
    except ImportError:
        return False
    try:
        with psycopg.connect(url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
        return True
    except Exception:
        return False


@pytest.mark.integration
def test_ingest_by_ean_e2e():
    try:
        from dotenv import load_dotenv

        load_dotenv()  # apanha workers/.env quando corrido localmente
    except ImportError:
        pass
    url = os.environ.get("DATABASE_URL")
    if not url or not _can_connect(url):
        pytest.skip("DATABASE_URL inacessível — skip do teste de integração e2e.")

    import psycopg

    from decifra_workers.config import Settings
    from decifra_workers.pipelines import ingest_by_ean

    # Limpa ingestões anteriores deste EAN (teste idempotente; source_records não
    # tem cascade, por isso apaga-se primeiro).
    with psycopg.connect(url, autocommit=True) as conn:
        ids = [
            r[0]
            for r in conn.execute(
                "SELECT product_id FROM product_identifiers WHERE id_value = %s", (EAN,)
            ).fetchall()
        ]
        if ids:
            conn.execute("DELETE FROM source_records WHERE product_id = ANY(%s)", (ids,))
            conn.execute("DELETE FROM products WHERE id = ANY(%s)", (ids,))

    result = ingest_by_ean(EAN, settings=Settings.from_env())
    assert result.status == "ok", f"ingestão falhou: {result.notes}"
    product_id = result.product_id
    assert product_id, "sem product_id no resultado"

    with psycopg.connect(url, autocommit=True) as conn:
        product = conn.execute(
            "SELECT brand, canonical_name FROM products WHERE id = %s", (product_id,)
        ).fetchone()
        assert product is not None, "golden record não foi criado"

        ean_ok = conn.execute(
            "SELECT 1 FROM product_identifiers WHERE product_id = %s AND id_value = %s",
            (product_id, EAN),
        ).fetchone()
        assert ean_ok is not None, "identificador EAN não foi gravado"

        n_specs = conn.execute(
            "SELECT count(*) FROM specs WHERE product_id = %s", (product_id,)
        ).fetchone()[0]
        assert n_specs >= 1, "esperava ≥1 spec (Icecat) gravada"

        n_sources = conn.execute(
            "SELECT count(*) FROM source_records WHERE product_id = %s", (product_id,)
        ).fetchone()[0]
        assert n_sources >= 1, "esperava ≥1 source_record"

        n_runs = conn.execute(
            "SELECT count(*) FROM ingestion_runs WHERE kind = 'on_demand' AND status = 'ok'"
        ).fetchone()[0]
        assert n_runs >= 1, "esperava ≥1 ingestion_run 'ok'"
