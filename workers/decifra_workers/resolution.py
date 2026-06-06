"""Entity resolution: resolve um RawRecord de identidade para products.id.

Estratégia (blueprint §2): EAN exato → fuzzy por marca+modelo (pg_trgm) →
criação de novo golden record (marcado needs_review se a confiança for baixa).
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import psycopg

from . import db
from .models import RawRecord

# Similaridade trigram mínima para um candidato a match fuzzy ser considerado.
# Não basta, por si só, para fundir: o token de modelo TEM de bater (ver
# resolve_product). O que separa XM4 de XM5 (similaridade 0.78) nunca foi o
# limiar — é a igualdade do modelo.
FUZZY_THRESHOLD = 0.6
# Merge fuzzy com similaridade abaixo deste valor fica marcado para revisão humana.
REVIEW_THRESHOLD = 0.8

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _model_key(text: str | None) -> str:
    """Chave discriminante do modelo: minúsculas, só alfanumérico.

    'WH-1000XM5' -> 'wh1000xm5'; 'iPhone 15 Pro' -> 'iphone15pro'. Modelos
    adjacentes (XM4 vs XM5, 15 vs 15 Pro) produzem chaves diferentes, pelo que
    não são fundidos mesmo quando a similaridade global da string é alta.
    """
    return _NON_ALNUM.sub("", (text or "").lower())


@dataclass
class Resolution:
    product_id: str
    created: bool
    method: str  # ean | fuzzy | created


def resolve_product(conn: psycopg.Connection, identity: RawRecord) -> Resolution:
    # 1. EAN exato
    if identity.ean:
        pid = db.find_product_by_ean(conn, identity.ean)
        if pid:
            return Resolution(pid, created=False, method="ean")

    # 2. Fuzzy por marca+modelo (cai para o nome se faltar), com guarda do modelo.
    name = " ".join(filter(None, [identity.brand, identity.model])) or (identity.name or "")
    match = db.fuzzy_match_product(conn, name, FUZZY_THRESHOLD)
    if match:
        pid, sim, cand_model = match
        new_key = _model_key(identity.model)
        cand_key = _model_key(cand_model)
        # Só fundimos se o token de modelo bater. Sem modelo nos dois lados, ou
        # com modelos diferentes, NÃO fundimos: criar um duplicado é recuperável,
        # fundir produtos distintos corrompe o golden record (e fá-lo em silêncio).
        if new_key and cand_key and new_key == cand_key:
            if sim < REVIEW_THRESHOLD:
                db.flag_needs_review(conn, pid, sim)
            return Resolution(pid, created=False, method="fuzzy")

    # 3. Criar golden record
    pid = db.create_product(
        conn,
        brand=identity.brand,
        model=identity.model,
        name=identity.name,
        summary=identity.summary,
        image_url=identity.image_url,
        match_confidence=identity.match_confidence,
        needs_review=identity.match_confidence < REVIEW_THRESHOLD,
    )
    return Resolution(pid, created=True, method="created")
