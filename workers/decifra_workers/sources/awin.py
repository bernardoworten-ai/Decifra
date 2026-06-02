"""Awin — ofertas (preço, imagem, deep link) a partir de um product feed.

Os feeds Awin são CSV (frequentemente gzip) com colunas configuráveis. Este
connector é de **batch**: percorre o feed e mapeia linhas → ofertas, casando por
EAN com o golden record. Requer a URL do feed (com a tua publisher key).
"""
from __future__ import annotations

import csv
import gzip
import io
from collections.abc import Iterator
from typing import Any

import httpx

from ..models import NormalizedOffer
from .base import SourceConnector

# Mapeamento tolerante de nomes de coluna comuns nos feeds Awin.
_COLS = {
    "ean": ("ean", "product_GTIN", "gtin"),
    "name": ("product_name", "product_short_description"),
    "price": ("search_price", "store_price", "price"),
    "currency": ("currency",),
    "url": ("aw_deep_link", "merchant_deep_link", "aw_product_id"),
    "in_stock": ("in_stock", "stock_status"),
    "merchant": ("merchant_name", "data_feed_name"),
}


def _pick(row: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return None


class AwinFeedConnector(SourceConnector):
    name = "awin_feed"
    kind = "offers"
    trust_weight = 0.8
    base_url = "https://productdata.awin.com"

    def __init__(self, feed_url: str | None = None):
        self.feed_url = feed_url

    def configured(self) -> bool:
        return bool(self.feed_url)

    @staticmethod
    def parse_rows(text: str) -> Iterator[tuple[str | None, NormalizedOffer, dict[str, Any]]]:
        """Itera (ean, oferta, linha-crua) a partir do CSV do feed."""
        reader = csv.DictReader(io.StringIO(text))
        for row in reader:
            price_raw = _pick(row, _COLS["price"])
            if not price_raw:
                continue
            try:
                price = float(str(price_raw).replace(",", "."))
            except ValueError:
                continue
            in_stock_raw = (_pick(row, _COLS["in_stock"]) or "1").lower()
            offer = NormalizedOffer(
                store_name=_pick(row, _COLS["merchant"]) or "Loja",
                price=price,
                currency=_pick(row, _COLS["currency"]) or "EUR",
                url_affiliate=_pick(row, _COLS["url"]),
                in_stock=in_stock_raw in ("1", "true", "yes", "in stock", "instock"),
            )
            yield _pick(row, _COLS["ean"]), offer, row

    def download(self) -> str:
        if not self.feed_url:
            raise RuntimeError("AWIN_FEED_URL não configurado.")
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            resp = client.get(self.feed_url)
        resp.raise_for_status()
        content = resp.content
        if self.feed_url.endswith(".gz") or content[:2] == b"\x1f\x8b":
            content = gzip.decompress(content)
        return content.decode("utf-8", errors="replace")
