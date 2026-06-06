"""Entity resolution (A1): o matcher fuzzy não pode fundir produtos distintos,
mas tem de continuar a fundir o mesmo produto, marcando para revisão os merges
de baixa confiança.

Os testes com `db_conn` requerem Postgres + pg_trgm (ver conftest; skip limpo
sem BD). `test_model_key_*` é offline e corre sempre.
"""
from __future__ import annotations

from decifra_workers import db
from decifra_workers.models import RawRecord
from decifra_workers.resolution import _model_key, resolve_product


def _seed(conn, *, brand, model, name=None, ean=None) -> str:
    pid = db.create_product(
        conn,
        brand=brand,
        model=model,
        name=name or f"{brand} {model}",
        summary=None,
        image_url=None,
        match_confidence=0.95,
        needs_review=False,
    )
    if ean:
        db.upsert_identifier(conn, pid, "ean", ean)
    return pid


def _rec(**kw) -> RawRecord:
    return RawRecord(source_name="t", source_kind="identity", **kw)


def _needs_review(conn, pid: str) -> bool:
    return conn.execute("SELECT needs_review FROM products WHERE id = %s", (pid,)).fetchone()[0]


# ---- offline (sem BD) ----

def test_model_key_normaliza():
    assert _model_key("WH-1000XM5") == "wh1000xm5"
    assert _model_key("iPhone 15 Pro") == "iphone15pro"
    assert _model_key(None) == ""
    # o discriminante: modelos adjacentes geram chaves diferentes
    assert _model_key("WH-1000XM4") != _model_key("WH-1000XM5")
    # variações triviais do mesmo modelo colapsam na mesma chave
    assert _model_key("WH-1000XM5") == _model_key("WH 1000 XM5")


# ---- com BD (pg_trgm) ----

def test_adjacentes_nao_fundem_xm4_xm5(db_conn):
    """XM4 já existe; ingerir XM5 (modelo diferente, sim 0.78) cria NOVO produto."""
    _seed(db_conn, brand="Sony", model="WH-1000XM4")
    r = resolve_product(db_conn, _rec(brand="Sony", model="WH-1000XM5", ean="111"))
    assert r.created is True
    assert r.method == "created"
    assert db_conn.execute("SELECT count(*) FROM products").fetchone()[0] == 2


def test_adjacentes_nao_fundem_iphone_15_pro(db_conn):
    """iPhone 15 existe; 15 Pro (sim 0.80) não pode fundir-se nele."""
    _seed(db_conn, brand="Apple", model="iPhone 15")
    r = resolve_product(db_conn, _rec(brand="Apple", model="iPhone 15 Pro", ean="222"))
    assert r.created is True
    assert db_conn.execute("SELECT count(*) FROM products").fetchone()[0] == 2


def test_mesmo_produto_funde_por_fuzzy(db_conn):
    """Mesmo brand+model, EAN diferente e nome variado: funde no existente, sem review."""
    pid = _seed(db_conn, brand="Sony", model="WH-1000XM5", ean="aaa")
    r = resolve_product(
        db_conn,
        _rec(brand="Sony", model="WH-1000XM5", name="Sony WH-1000XM5 Auscultadores", ean="bbb"),
    )
    assert r.created is False
    assert r.method == "fuzzy"
    assert r.product_id == pid
    assert _needs_review(db_conn, pid) is False
    assert db_conn.execute("SELECT count(*) FROM products").fetchone()[0] == 1


def test_merge_baixa_confianca_marca_review(db_conn):
    """Mesmo modelo mas brand em falta (sim ~0.69 < 0.8): funde MAS marca needs_review."""
    pid = _seed(db_conn, brand="Sony", model="WH-1000XM5", ean="aaa")
    r = resolve_product(db_conn, _rec(brand=None, model="WH-1000XM5", ean="ccc"))
    assert r.created is False
    assert r.method == "fuzzy"
    assert r.product_id == pid
    assert _needs_review(db_conn, pid) is True


def test_ean_exato_tem_prioridade(db_conn):
    """EAN conhecido resolve por EAN (não cria nem faz fuzzy)."""
    pid = _seed(db_conn, brand="Sony", model="WH-1000XM5", ean="555")
    r = resolve_product(db_conn, _rec(brand="Sony", model="WH-1000XM5", ean="555"))
    assert r.created is False
    assert r.method == "ean"
    assert r.product_id == pid
