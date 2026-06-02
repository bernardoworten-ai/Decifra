"""Open Icecat — specs por GTIN/EAN.

Open Icecat é grátis para o subconjunto aberto; basta um UserName registado.
Endpoint JSON: https://live.icecat.biz/api?UserName=...&Language=PT&GTIN=...&Content=ALL
"""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..models import NormalizedSpec, RawRecord
from ..text_utils import slugify
from .base import SourceConnector


class _Retryable(Exception):
    pass


class IcecatConnector(SourceConnector):
    name = "icecat"
    kind = "specs"
    trust_weight = 0.9
    base_url = "https://live.icecat.biz/api"

    def __init__(self, username: str | None = None, language: str = "PT"):
        self.username = username
        self.language = language

    def configured(self) -> bool:
        return bool(self.username)

    @staticmethod
    def parse(payload: dict[str, Any], fallback_ean: str) -> RawRecord | None:
        data = payload.get("data") or payload
        general = data.get("GeneralInfo") or {}
        brand = general.get("Brand") or general.get("BrandInfo", {}).get("BrandName")
        model = general.get("ProductName") or general.get("Title")
        title = general.get("Title") or " ".join(filter(None, [brand, model]))

        image = None
        if isinstance(data.get("Image"), dict):
            image = data["Image"].get("HighPic") or data["Image"].get("Pic")

        specs: list[NormalizedSpec] = []
        for group in data.get("FeaturesGroups") or []:
            for feature in group.get("Features") or []:
                fname = (feature.get("Feature") or {}).get("Name", {})
                label = fname.get("Value") if isinstance(fname, dict) else str(fname)
                if not label:
                    continue
                raw_value = feature.get("PresentationValue") or feature.get("Value")
                if raw_value in (None, ""):
                    continue
                value_num = None
                try:
                    value_num = float(str(feature.get("RawValue") or "").replace(",", "."))
                except (TypeError, ValueError):
                    pass
                specs.append(
                    NormalizedSpec(
                        key=slugify(label),
                        value_text=str(raw_value),
                        value_num=value_num,
                        unit=(feature.get("Measure") or {}).get("Sign") or None,
                        confidence=0.9,
                    )
                )

        if not (title or specs):
            return None
        return RawRecord(
            source_name="icecat",
            source_kind="specs",
            ean=fallback_ean,
            name=title,
            brand=brand,
            model=model,
            image_url=image,
            summary=general.get("SummaryDescription", {}).get("LongSummaryDescription")
            if isinstance(general.get("SummaryDescription"), dict)
            else None,
            specs=specs,
            raw_payload=data,
            match_confidence=0.9,
        )

    @retry(
        retry=retry_if_exception_type(_Retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        reraise=True,
    )
    def fetch_by_ean(self, ean: str) -> RawRecord | None:
        if not self.configured():
            return None
        params = {
            "UserName": self.username,
            "Language": self.language,
            "GTIN": ean,
            "Content": "ALL",
        }
        with httpx.Client(timeout=20) as client:
            resp = client.get(self.base_url, params=params)
        if resp.status_code in (400, 404):
            return None
        if resp.status_code == 429 or resp.status_code >= 500:
            raise _Retryable(f"icecat {resp.status_code}")
        resp.raise_for_status()
        body = resp.json()
        # Icecat devolve {"msg": "...", "data": {...}} — sem data ⇒ não encontrado.
        if not body.get("data"):
            return None
        return self.parse(body, ean)
