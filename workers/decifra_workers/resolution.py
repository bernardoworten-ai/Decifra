"""Entity resolution: resolve um RawRecord de identidade para products.id.

Estratégia (blueprint §2): EAN exato → fuzzy por marca+modelo (pg_trgm) →
criação de novo golden record (marcado needs_review se a confiança for baixa).
"""
from __future__ import annotations

from dataclasses import dataclass

import psycopg

from . import db
from .models import RawRecord

# Acima deste limite de similaridade, consideramos o mesmo produto.
FUZZY_THRESHOLD = 0.55
# Abaixo desta confiança de merge, o produto fica marcado para revisão humana.
REVIEW_THRESHOLD = 0.8


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

    # 2. Fuzzy por marca+modelo (cai para o nome se faltar)
    name = " ".join(filter(None, [identity.brand, identity.model])) or (identity.name or "")
    match = db.fuzzy_match_product(conn, name, FUZZY_THRESHOLD)
    if match:
        return Resolution(match[0], created=False, method="fuzzy")

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
