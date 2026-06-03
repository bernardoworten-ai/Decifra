"""Testes do parser de preço live — offline (sem rede)."""
from __future__ import annotations

from decifra_workers.config import Settings
from decifra_workers.sources import price_live as pl


def test_parse_serpapi():
    payload = {
        "shopping_results": [
            {"source": "Worten", "price": "€349,99", "extracted_price": 349.99, "product_link": "https://w/x"},
            {"source": "Fnac", "price": "€359.00", "extracted_price": 359.0, "link": "https://f/y"},
            {"source": "SemPreço"},  # ignorado: sem extracted_price
        ]
    }
    offers = pl.parse_serpapi(payload)
    assert len(offers) == 2
    assert offers[0].store_name == "Worten" and offers[0].price == 349.99
    assert offers[0].currency == "EUR" and offers[0].url_affiliate == "https://w/x"


def test_parse_dataforseo():
    offers = pl.parse_dataforseo({"items": [{"seller": "Amazon.es", "price": "339.90", "currency": "EUR", "url": "https://a/z"}]})
    assert offers[0].store_name == "Amazon.es" and offers[0].price == 339.9


def test_parse_brightdata():
    offers = pl.parse_brightdata({"results": [{"merchant": "PCDIGA", "final_price": 149.99, "url": "https://p/q"}]})
    assert offers[0].store_name == "PCDIGA" and offers[0].price == 149.99


def test_currency_detection():
    assert pl._currency("€10") == "EUR"
    assert pl._currency("$10") == "USD"
    assert pl._currency("£10") == "GBP"
    assert pl._currency("10") is None


def test_connector_not_configured_is_graceful():
    c = pl.PriceLiveConnector(Settings(database_url="x"))  # sem qualquer provider
    assert c.configured() is False
    assert c.fetch("4548736132917", "Sony") == []
