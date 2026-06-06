"""UPCitemdb — identidade por EAN/UPC.

O endpoint *trial* funciona sem credenciais (rate-limited ~100/dia/IP), o que o
torna ideal para arrancar. Com chave, usa-se o endpoint de produção.
"""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..models import RawRecord
from .base import SourceConnector


class _Retryable(Exception):
    pass


class UpcItemDbConnector(SourceConnector):
    name = "upcitemdb"
    kind = "identity"
    trust_weight = 0.7
    base_url = "https://api.upcitemdb.com"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key

    def configured(self) -> bool:
        return True  # endpoint trial não exige credenciais

    @staticmethod
    def parse(payload: dict[str, Any], fallback_ean: str) -> RawRecord | None:
        items = payload.get("items") or []
        if not items:
            return None
        it = items[0]
        images = it.get("images") or []
        return RawRecord(
            source_name="upcitemdb",
            source_kind="identity",
            ean=it.get("ean") or fallback_ean,
            name=it.get("title"),
            brand=it.get("brand") or None,
            model=it.get("model") or None,
            image_url=images[0] if images else None,
            summary=it.get("description") or None,
            raw_payload=it,
            match_confidence=0.85,
        )

    @retry(
        retry=retry_if_exception_type(_Retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        reraise=True,
    )
    def fetch_by_ean(self, ean: str) -> RawRecord | None:
        endpoint = "trial" if not self.api_key else "v1"
        url = f"{self.base_url}/prod/{endpoint}/lookup"
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["user_key"] = self.api_key
        with httpx.Client(timeout=15) as client:
            resp = client.get(url, params={"upc": ean}, headers=headers)
        if resp.status_code in (400, 404):
            return None  # UPC inválido ou não encontrado — não vale retry
        if resp.status_code == 429 or resp.status_code >= 500:
            raise _Retryable(f"upcitemdb {resp.status_code}")
        resp.raise_for_status()
        return self.parse(resp.json(), ean)
