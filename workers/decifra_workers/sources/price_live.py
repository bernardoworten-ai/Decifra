"""Preço live (§3/§7) — SÓ on-demand (botão "atualizar"), nunca em batch (§10).

Connector económico sobre Google Shopping via DataForSEO (login+password) ou
Bright Data (token); SerpApi (SERPAPI_KEY) como alternativa. Escolhe a fonte mais
barata configurada. Devolve ofertas atuais como NormalizedOffer. Graceful: lista
vazia em falha/sem credenciais. Cada parser é puro e testável.
"""
from __future__ import annotations

import os

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import Settings
from ..models import NormalizedOffer


class _Retryable(Exception):
    pass


def _currency(price_text: str | None) -> str | None:
    if not price_text:
        return None
    if "€" in price_text:
        return "EUR"
    if "£" in price_text:
        return "GBP"
    if "$" in price_text:
        return "USD"
    return None


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def parse_serpapi(payload: dict) -> list[NormalizedOffer]:
    offers: list[NormalizedOffer] = []
    for r in payload.get("shopping_results") or []:
        price = _num(r.get("extracted_price"))
        if price is None:
            continue
        offers.append(
            NormalizedOffer(
                store_name=r.get("source") or r.get("seller") or "Loja",
                price=price,
                currency=_currency(r.get("price")) or "EUR",
                url_affiliate=r.get("product_link") or r.get("link"),
                in_stock=True,
            )
        )
    return offers


def parse_dataforseo(payload: dict) -> list[NormalizedOffer]:
    """Mapeia uma resposta tipo DataForSEO Merchant/Google Shopping → ofertas.
    Best-effort; confirmar os nomes dos campos contra o schema vivo."""
    items = payload.get("items") or []
    offers: list[NormalizedOffer] = []
    for it in items:
        price = _num(it.get("price") or (it.get("price_info") or {}).get("current_price"))
        if price is None:
            continue
        offers.append(
            NormalizedOffer(
                store_name=it.get("seller") or it.get("shop") or it.get("source") or "Loja",
                price=price,
                currency=it.get("currency") or "EUR",
                url_affiliate=it.get("url") or it.get("link"),
                in_stock=it.get("availability", True) not in (False, "out_of_stock"),
            )
        )
    return offers


def parse_brightdata(payload: dict) -> list[NormalizedOffer]:
    rows = payload.get("results") or payload.get("data") or []
    offers: list[NormalizedOffer] = []
    for r in rows:
        price = _num(r.get("price") or r.get("final_price"))
        if price is None:
            continue
        offers.append(
            NormalizedOffer(
                store_name=r.get("seller") or r.get("merchant") or "Loja",
                price=price,
                currency=r.get("currency") or "EUR",
                url_affiliate=r.get("url") or r.get("link"),
                in_stock=True,
            )
        )
    return offers


class PriceLiveConnector:
    """Escolhe o provider mais barato configurado (DataForSEO > Bright Data > SerpApi)."""

    kind = "offers"

    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.dataforseo_login and settings.dataforseo_password:
            self.provider = "dataforseo"
        elif settings.brightdata_token:
            self.provider = "brightdata"
        elif settings.serpapi_key:
            self.provider = "serpapi"
        else:
            self.provider = None

    @property
    def source_name(self) -> str:
        return self.provider or "price_live"

    def configured(self) -> bool:
        return self.provider is not None

    @retry(
        retry=retry_if_exception_type(_Retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        reraise=True,
    )
    def _get(self, *args, **kwargs) -> httpx.Response:
        resp = httpx.get(*args, timeout=30, **kwargs)
        if resp.status_code == 429 or resp.status_code >= 500:
            raise _Retryable(f"{resp.status_code}")
        resp.raise_for_status()
        return resp

    def fetch(self, ean: str | None, title: str | None) -> list[NormalizedOffer]:
        """Ofertas atuais para um EAN/título. Lista vazia em falha (graceful)."""
        if not self.configured():
            return []
        query = ean or title
        if not query:
            return []
        try:
            if self.provider == "serpapi":
                base = os.environ.get("SERPAPI_BASE_URL", "https://serpapi.com")
                resp = self._get(
                    f"{base}/search.json",
                    params={
                        "engine": "google_shopping",
                        "q": query,
                        "gl": "pt",
                        "hl": "pt",
                        "api_key": self.settings.serpapi_key,
                    },
                )
                return parse_serpapi(resp.json())
            if self.provider == "brightdata":
                base = os.environ.get("BRIGHTDATA_BASE_URL", "https://api.brightdata.com")
                resp = self._get(
                    f"{base}/serp/google/shopping",
                    params={"q": query, "country": "pt"},
                    headers={"Authorization": f"Bearer {self.settings.brightdata_token}"},
                )
                return parse_brightdata(resp.json())
            if self.provider == "dataforseo":
                base = os.environ.get("DATAFORSEO_BASE_URL", "https://api.dataforseo.com")
                resp = httpx.post(
                    f"{base}/v3/merchant/google/products/live/advanced",
                    auth=(self.settings.dataforseo_login or "", self.settings.dataforseo_password or ""),
                    json=[{"keyword": query, "location_code": 2620, "language_code": "pt"}],
                    timeout=30,
                )
                resp.raise_for_status()
                tasks = resp.json().get("tasks") or []
                result = (tasks[0].get("result") or [{}])[0] if tasks else {}
                return parse_dataforseo(result)
        except Exception:
            return []  # graceful: nunca quebra o pedido on-demand
        return []
