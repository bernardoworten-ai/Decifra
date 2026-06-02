"""Awin — ofertas (preço, imagem, deep link) a partir de um product feed.

Os feeds Awin são CSV (normalmente gzip) e podem ter centenas de MB. Este
connector faz **streaming** (gunzip incremental + CSV em fluxo), para casar por
EAN com o golden record e poder parar cedo (limit) sem descarregar tudo.
Requer a URL do feed (AWIN_FEED_URL, com a tua publisher key).
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
    "price": ("search_price", "store_price", "price"),
    "currency": ("currency",),
    "url": ("aw_deep_link", "merchant_deep_link"),
    "in_stock": ("in_stock", "stock_status"),
    "merchant": ("merchant_name", "data_feed_name"),
}
_IN_STOCK_TRUE = {"1", "true", "yes", "in stock", "instock"}


def _pick(row: dict[str, str], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return None


def _row_to_offer(row: dict[str, str]) -> tuple[str | None, NormalizedOffer] | None:
    price_raw = _pick(row, _COLS["price"])
    if not price_raw:
        return None
    try:
        price = float(str(price_raw).replace(",", "."))
    except ValueError:
        return None
    in_stock_raw = (_pick(row, _COLS["in_stock"]) or "1").lower()
    offer = NormalizedOffer(
        store_name=_pick(row, _COLS["merchant"]) or "Loja",
        price=price,
        currency=_pick(row, _COLS["currency"]) or "EUR",
        url_affiliate=_pick(row, _COLS["url"]),
        in_stock=in_stock_raw in _IN_STOCK_TRUE,
    )
    return _pick(row, _COLS["ean"]), offer


class _IteratorReader(io.RawIOBase):
    """Adapta um iterador de bytes (httpx stream) a um file-like legível."""

    def __init__(self, chunks: Iterator[bytes]):
        self._chunks = chunks
        self._buf = b""

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:  # type: ignore[override]
        while not self._buf:
            try:
                self._buf = next(self._chunks)
            except StopIteration:
                return 0
        n = min(len(b), len(self._buf))
        b[:n], self._buf = self._buf[:n], self._buf[n:]
        return n


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
        """Parse de um CSV completo em memória (usado nos testes offline)."""
        for row in csv.DictReader(io.StringIO(text)):
            res = _row_to_offer(row)
            if res:
                yield res[0], res[1], row

    def stream_rows(
        self, limit: int | None = None
    ) -> Iterator[tuple[str | None, NormalizedOffer, dict[str, Any]]]:
        """Streaming do feed: gunzip incremental + CSV em fluxo. Para após `limit`."""
        if not self.feed_url:
            raise RuntimeError("AWIN_FEED_URL não configurado.")
        is_gzip = "compression/gzip" in self.feed_url or self.feed_url.endswith(".gz")
        with httpx.Client(timeout=300, follow_redirects=True) as client:
            with client.stream("GET", self.feed_url) as resp:
                resp.raise_for_status()
                raw = _IteratorReader(resp.iter_bytes())
                binary = gzip.GzipFile(fileobj=raw) if is_gzip else raw
                text = io.TextIOWrapper(binary, encoding="utf-8", errors="replace")
                yielded = 0
                for row in csv.DictReader(text):
                    res = _row_to_offer(row)
                    if not res:
                        continue
                    yield res[0], res[1], row
                    yielded += 1
                    if limit and yielded >= limit:
                        break
