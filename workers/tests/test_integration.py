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

    if not os.environ.get("ICECAT_USERNAME"):
        pytest.skip(
            "ICECAT_USERNAME ausente — sem fonte de specs para o e2e live; "
            "usa test_ingest_by_ean_e2e_mocked (determinístico)."
        )

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


@pytest.mark.integration
def test_icecat_open_resolves_specs():
    """Open Icecat (só UserName, sem app_key) devolve specs para um GTIN real."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    username = os.environ.get("ICECAT_USERNAME")
    if not username:
        pytest.skip("ICECAT_USERNAME não definido — skip do teste live do Icecat.")

    from decifra_workers.sources.icecat import IcecatConnector

    rec = IcecatConnector(
        username=username, app_key=os.environ.get("ICECAT_APP_KEY") or None
    ).fetch_by_ean("4948570114344")
    assert rec is not None, "Icecat não devolveu dados — verifica ICECAT_USERNAME"
    assert len(rec.specs) >= 80, f"esperava ≥80 specs, obteve {len(rec.specs)}"


@pytest.mark.integration
def test_ingest_by_ean_e2e_mocked(monkeypatch):
    """e2e determinístico: build_connectors mockado (sem rede/credenciais)."""
    url = os.environ.get("DATABASE_URL")
    if not url or not _can_connect(url):
        pytest.skip("DATABASE_URL inacessível — skip do e2e mockado.")

    import psycopg

    from decifra_workers import pipelines
    from decifra_workers.config import Settings
    from decifra_workers.models import NormalizedSpec, RawRecord
    from decifra_workers.sources.base import SourceConnector

    EAN = "0000000000017"  # EAN de teste, fora do seed

    class _FakeIdentity(SourceConnector):
        name = "fake_identity"
        kind = "identity"
        trust_weight = 0.7
        base_url = "https://example.test/identity"

        def configured(self) -> bool:
            return True

        def fetch_by_ean(self, ean: str) -> RawRecord | None:
            return RawRecord(
                source_name=self.name, source_kind=self.kind, ean=ean,
                name="Produto de Teste X1", brand="TestBrand", model="X1",
                raw_payload={"ean": ean, "src": self.name}, match_confidence=0.95,
            )

    class _FakeSpecs(SourceConnector):
        name = "fake_specs"
        kind = "specs"
        trust_weight = 0.9
        base_url = "https://example.test/specs"

        def configured(self) -> bool:
            return True

        def fetch_by_ean(self, ean: str) -> RawRecord | None:
            return RawRecord(
                source_name=self.name, source_kind=self.kind, ean=ean,
                brand="TestBrand", model="X1",
                specs=[
                    NormalizedSpec(key="Peso", value_num=1.2, unit="kg", confidence=0.9),
                    NormalizedSpec(key="Cor", value_text="Preto", confidence=0.9),
                ],
                raw_payload={"ean": ean, "src": self.name}, match_confidence=0.9,
            )

    monkeypatch.setattr(
        pipelines, "build_connectors",
        lambda settings: [_FakeIdentity(), _FakeSpecs()],
    )
    # Defensivo: sem rede também na IA. Ajusta o alvo se o import de `ai` diferir.
    monkeypatch.setattr(pipelines.ai, "summarize_product", lambda rec: "", raising=False)

    with psycopg.connect(url, autocommit=True) as conn:  # limpeza idempotente
        ids = [r[0] for r in conn.execute(
            "SELECT product_id FROM product_identifiers WHERE id_value = %s", (EAN,)).fetchall()]
        if ids:
            conn.execute("DELETE FROM source_records WHERE product_id = ANY(%s)", (ids,))
            conn.execute("DELETE FROM products WHERE id = ANY(%s)", (ids,))

    result = pipelines.ingest_by_ean(EAN, settings=Settings(database_url=url))
    assert result.status == "ok", f"ingestão falhou: {result.notes}"
    pid = result.product_id
    assert pid, "sem product_id"

    with psycopg.connect(url, autocommit=True) as conn:
        assert conn.execute("SELECT 1 FROM products WHERE id = %s", (pid,)).fetchone()
        assert conn.execute(
            "SELECT 1 FROM product_identifiers WHERE product_id = %s AND id_value = %s",
            (pid, EAN)).fetchone()
        assert conn.execute(
            "SELECT count(*) FROM specs WHERE product_id = %s", (pid,)).fetchone()[0] >= 2
        assert conn.execute(
            "SELECT count(*) FROM source_records WHERE product_id = %s", (pid,)).fetchone()[0] >= 2
        assert conn.execute(
            "SELECT 1 FROM ingestion_runs WHERE kind = 'on_demand' AND status = 'ok'").fetchone()
