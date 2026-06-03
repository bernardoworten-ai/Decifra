"""Reviews: parsers (só métricas, nunca texto) + nota ajustada — offline."""
from __future__ import annotations

import dataclasses

from decifra_workers import ai, scoring
from decifra_workers.sources import reviews

JSONLD = """
<html><head>
<script type="application/ld+json">
{"@type":"Product","name":"X",
 "aggregateRating":{"@type":"AggregateRating","ratingValue":"4.6","reviewCount":"1250"},
 "review":[{"@type":"Review","reviewRating":{"ratingValue":5},"datePublished":"2026-05-01"},
           {"@type":"Review","reviewRating":{"ratingValue":2},"datePublished":"2026-05-10"}],
 "positiveNotes":{"@type":"ItemList","itemListElement":[{"@type":"ListItem","name":"Boa autonomia"}]},
 "negativeNotes":{"@type":"ItemList","itemListElement":[{"@type":"ListItem","name":"Preço alto"}]}}
</script></head><body>...</body></html>
"""


def test_parse_jsonld_metrics_only():
    m = reviews.parse_jsonld(JSONLD, "https://x.pt/p", "x")
    assert m is not None
    assert m.rating == 4.6 and m.review_count == 1250
    assert m.distribution == {"5": 1, "2": 1}
    assert m.last_review_at == "2026-05-10"
    assert ("Boa autonomia", "positivo") in m.theme_tokens
    assert ("Preço alto", "negativo") in m.theme_tokens


def test_parse_jsonld_none_without_data():
    assert reviews.parse_jsonld("<html></html>", "u", "s") is None


def test_parse_jsonld_never_keeps_review_text():
    html = JSONLD.replace('"datePublished":"2026-05-10"', '"datePublished":"2026-05-10","reviewBody":"texto secreto"')
    m = reviews.parse_jsonld(html, "u", "s")
    assert "texto secreto" not in str(dataclasses.asdict(m))


def test_parse_dataforseo_shape():
    payload = {
        "rating": {"value": "4.2", "votes_count": "800"},
        "reviews_count": 800,
        "rating_distribution": {"5": 600, "1": 50},
        "keywords": [{"keyword": "bateria", "sentiment": "positive"}],
    }
    m = reviews.parse_dataforseo(payload, "u", "google")
    assert m.rating == 4.2 and m.review_count == 800
    assert m.distribution == {"5": 600, "1": 50}
    assert ("bateria", "positivo") in m.theme_tokens


def test_adjusted_rating():
    assert scoring.adjusted_rating(4.6, None) == 4.6  # sem autenticidade → nota crua
    assert scoring.adjusted_rating(None, 0.9) is None
    low = scoring.adjusted_rating(5.0, 0.0)
    high = scoring.adjusted_rating(5.0, 1.0)
    assert 3.0 < low < high <= 5.0  # baixa autenticidade puxa para o neutro


def test_ai_graceful_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ai.review_authenticity({"rating": 4.5}) is None
    assert ai.review_themes_summary([("x", "positivo")]) is None
