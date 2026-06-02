"""Teste offline do parser de feed Awin (CSV → ofertas)."""
from __future__ import annotations

from decifra_workers.sources.awin import AwinFeedConnector

CSV = (
    "product_name,ean,search_price,currency,aw_deep_link,in_stock,merchant_name\n"
    "Sony WH-1000XM5,4548736132917,349.99,EUR,https://awin1.com/x,1,Worten\n"
    "Sem preço,1111111111111,,EUR,https://awin1.com/y,1,Fnac\n"
    "Bose QC Ultra,0017817845476,399,EUR,https://awin1.com/z,0,Amazon\n"
)


def test_parse_rows():
    rows = list(AwinFeedConnector.parse_rows(CSV))
    # A linha sem preço é ignorada.
    assert len(rows) == 2
    ean0, offer0, _ = rows[0]
    assert ean0 == "4548736132917"
    assert offer0.store_name == "Worten"
    assert offer0.price == 349.99
    assert offer0.in_stock is True
    _, offer1, _ = rows[1]
    assert offer1.in_stock is False  # '0' → sem stock
