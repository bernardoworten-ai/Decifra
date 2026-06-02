"""Estruturas normalizadas que os connectors devolvem (antes do merge)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NormalizedSpec:
    key: str
    value_text: str | None = None
    value_num: float | None = None
    unit: str | None = None
    confidence: float = 0.6


@dataclass
class NormalizedOffer:
    store_name: str
    price: float
    currency: str = "EUR"
    url_affiliate: str | None = None
    in_stock: bool = True


@dataclass
class RawRecord:
    """O resultado de um connector para um (EAN, fonte). Cru + normalizado.

    `raw_payload` é guardado em source_records para auditoria/re-matching;
    os campos normalizados alimentam o golden record com source_id+confidence.
    """

    source_name: str
    source_kind: str  # identity | specs | offers | reviews | expert
    ean: str | None = None
    name: str | None = None
    brand: str | None = None
    model: str | None = None
    image_url: str | None = None
    summary: str | None = None
    specs: list[NormalizedSpec] = field(default_factory=list)
    offers: list[NormalizedOffer] = field(default_factory=list)
    raw_payload: dict[str, Any] | None = None
    match_confidence: float = 0.8
