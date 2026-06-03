"""Connector de reviews — MÉTRICAS públicas por plataforma (§5).

CRÍTICO/LEGAL: nunca extrair nem guardar o TEXTO das reviews. Só métricas
(nota, volume, distribuição, recência), temas DERIVADOS (pros/cons / keywords) e
o link à fonte. Respeita robots/ToS (best-effort) — se não for permitido recolher,
devolve None (mostra-se só a nota pública + link a montante).

Fontes:
- JsonLdReviewsConnector: lê schema.org `aggregateRating` (+ datas/notas para
  distribuição/recência, + positiveNotes/negativeNotes como temas) de uma página
  pública. Sem credenciais. NUNCA lê reviewBody.
- DataForSeoReviewsConnector: via DataForSEO (Google/Trustpilot), gated em creds.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx


@dataclass
class ReviewMetrics:
    source_name: str
    source_url: str
    rating: float | None  # 0-5 (nota média pública)
    review_count: int
    distribution: dict[str, int]  # {"5": n, ...} (pode ser {})
    last_review_at: str | None  # ISO date (recência) — métrica, não texto
    theme_tokens: list[tuple[str, str]] = field(default_factory=list)  # [(tema, 'positivo'|'negativo')]
    trust_weight: float = 0.6


# ──────────────────────────── helpers de parsing ────────────────────────────
def _num(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _int(v) -> int:
    try:
        return int(float(str(v).replace(",", ".")))
    except (TypeError, ValueError):
        return 0


def _notes(node) -> list[str]:
    """Extrai rótulos curtos de positiveNotes/negativeNotes (pros/cons), nunca texto longo."""
    if not node:
        return []
    items = node.get("itemListElement") if isinstance(node, dict) else node
    out = []
    for it in items or []:
        name = it.get("name") if isinstance(it, dict) else str(it)
        if name:
            out.append(str(name).strip()[:80])
    return out


def _iter_jsonld(html: str):
    for m in re.finditer(
        r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S | re.I
    ):
        try:
            data = json.loads(m.group(1).strip())
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and "@graph" in data:
            yield from data["@graph"]
        elif isinstance(data, list):
            yield from data
        else:
            yield data


def parse_jsonld(html: str, source_url: str, source_name: str) -> ReviewMetrics | None:
    """Extrai métricas de reviews de JSON-LD schema.org. NUNCA lê reviewBody."""
    agg = None
    reviews: list[dict] = []
    pos: list[str] = []
    neg: list[str] = []
    for n in _iter_jsonld(html):
        if not isinstance(n, dict):
            continue
        if isinstance(n.get("aggregateRating"), dict):
            agg = n["aggregateRating"]
        if n.get("@type") == "AggregateRating":
            agg = n
        rev = n.get("review")
        if isinstance(rev, list):
            reviews += [r for r in rev if isinstance(r, dict)]
        elif isinstance(rev, dict):
            reviews.append(rev)
        if n.get("@type") == "Review":
            reviews.append(n)
        pos += _notes(n.get("positiveNotes"))
        neg += _notes(n.get("negativeNotes"))

    if not agg and not reviews:
        return None

    rating = _num(agg.get("ratingValue")) if agg else None
    count = _int(agg.get("reviewCount") or agg.get("ratingCount")) if agg else 0

    # Distribuição + recência derivadas das NOTAS/DATAS (nunca do texto).
    dist: dict[str, int] = {}
    dates: list[str] = []
    for r in reviews:
        rr = r.get("reviewRating") if isinstance(r.get("reviewRating"), dict) else {}
        rv = _num(rr.get("ratingValue"))
        if rv is not None:
            star = str(int(round(rv)))
            dist[star] = dist.get(star, 0) + 1
        d = r.get("datePublished")
        if d:
            dates.append(str(d)[:10])
    if not count and reviews:
        count = len(reviews)
    last = max(dates) if dates else None

    tokens = [(t, "positivo") for t in pos] + [(t, "negativo") for t in neg]
    return ReviewMetrics(source_name, source_url, rating, count, dist, last, tokens)


def parse_dataforseo(payload: dict, source_url: str, source_name: str) -> ReviewMetrics | None:
    """Mapeia uma resposta tipo DataForSEO (Google/Trustpilot) para métricas.

    Best-effort: os nomes exatos dos campos devem ser confirmados contra o schema
    vivo da DataForSEO. Só métricas + keywords (temas) — nunca o texto."""
    rating_obj = payload.get("rating") if isinstance(payload.get("rating"), dict) else None
    rating = _num(rating_obj.get("value") if rating_obj else payload.get("rating"))
    count = _int(payload.get("reviews_count") or (rating_obj.get("votes_count") if rating_obj else None))
    dist = {str(k): _int(v) for k, v in (payload.get("rating_distribution") or {}).items()}
    last = payload.get("last_review_timestamp") or payload.get("last_review_at")
    tokens: list[tuple[str, str]] = []
    for kw in payload.get("keywords") or []:
        if isinstance(kw, dict) and kw.get("keyword"):
            pol = "positivo" if (kw.get("sentiment") or "").lower().startswith("pos") else "negativo"
            tokens.append((str(kw["keyword"])[:80], pol))
    if rating is None and count == 0:
        return None
    return ReviewMetrics(source_name, source_url, rating, count, dist, (str(last)[:10] if last else None), tokens, 0.7)


# ──────────────────────────────── robots/ToS ────────────────────────────────
def robots_allows(url: str, user_agent: str = "DecifraBot") -> bool:
    """Verificação best-effort de robots.txt (allow em caso de erro)."""
    try:
        p = urlparse(url)
        robots = f"{p.scheme}://{p.netloc}/robots.txt"
        resp = httpx.get(robots, timeout=5)
        if resp.status_code != 200:
            return True
        disallow: list[str] = []
        applies = False
        for line in resp.text.splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            key, _, val = line.partition(":")
            key, val = key.strip().lower(), val.strip()
            if key == "user-agent":
                applies = val == "*" or val.lower() == user_agent.lower()
            elif key == "disallow" and applies and val:
                disallow.append(val)
        return not any(p.path.startswith(d) for d in disallow)
    except Exception:
        return True


# ────────────────────────────────  connectors  ──────────────────────────────
def _source_from_host(url: str) -> str:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    return host.split(".")[0] if host else "reviews"


class JsonLdReviewsConnector:
    name = "jsonld_reviews"
    kind = "reviews"

    def __init__(self, url: str, source_name: str | None = None):
        self.url = url
        self.source_name = source_name or _source_from_host(url)

    def configured(self) -> bool:
        return bool(self.url)

    def fetch_metrics(self) -> ReviewMetrics | None:
        if not self.url or not robots_allows(self.url):
            return None
        try:
            resp = httpx.get(self.url, timeout=15, follow_redirects=True, headers={"User-Agent": "DecifraBot"})
            resp.raise_for_status()
        except Exception as exc:
            from .. import observability

            observability.capture(exc, source=self.source_name, kind="reviews", url=self.url)
            return None
        return parse_jsonld(resp.text, self.url, self.source_name)


class DataForSeoReviewsConnector:
    name = "dataforseo_reviews"
    kind = "reviews"
    base_url = "https://api.dataforseo.com"

    def __init__(self, login: str | None, password: str | None):
        self.login = login
        self.password = password

    def configured(self) -> bool:
        return bool(self.login and self.password)

    def fetch_metrics(self, query: str, source_name: str = "google") -> ReviewMetrics | None:
        if not self.configured():
            return None
        try:
            resp = httpx.post(
                f"{self.base_url}/v3/business_data/google/reviews/live",
                auth=(self.login or "", self.password or ""),
                json=[{"keyword": query}],
                timeout=30,
            )
            resp.raise_for_status()
            tasks = resp.json().get("tasks") or []
            result = (tasks[0].get("result") or [{}])[0] if tasks else {}
        except Exception:
            return None
        return parse_dataforseo(result, self.base_url, source_name)
