"""Open/Full Icecat — specs por GTIN/EAN.

Endpoint JSON: https://live.icecat.biz/api?UserName=...&Language=PT&GTIN=...&Content=ALL

A API live exige `UserName`; o conteúdo Full Icecat exige adicionalmente um
`app_key` (ICECAT_APP_KEY, em "Meu Perfil" no Icecat). Sem app_key só se acede
ao subconjunto Open Icecat — e produtos fora dele devolvem 403 (tratado como skip).
"""
from __future__ import annotations

import sys
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

    def __init__(
        self, username: str | None = None, app_key: str | None = None, language: str = "PT"
    ):
        self.username = username
        self.app_key = app_key
        self.language = language
        self._warned_appkey = False

    def configured(self) -> bool:
        # UserName basta para Open Icecat; app_key é necessário para Full Icecat.
        return bool(self.username)

    @staticmethod
    def parse(payload: dict[str, Any], fallback_ean: str) -> RawRecord | None:
        data = payload.get("data") or payload
        general = data.get("GeneralInfo") or {}
        brand = general.get("Brand") or (general.get("BrandInfo") or {}).get("BrandName")
        model = general.get("ProductName") or general.get("Title")
        title = general.get("Title") or " ".join(filter(None, [brand, model]))

        image = None
        if isinstance(data.get("Image"), dict):
            image = data["Image"].get("HighPic") or data["Image"].get("Pic")

        specs: list[NormalizedSpec] = []
        # A API já usou "FeaturesGroups" e "FeatureGroups" — toleramos ambos.
        for group in data.get("FeaturesGroups") or data.get("FeatureGroups") or []:
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
                measure = feature.get("Measure") or {}
                specs.append(
                    NormalizedSpec(
                        key=slugify(label),
                        value_text=str(raw_value),
                        value_num=value_num,
                        unit=(measure.get("Sign") if isinstance(measure, dict) else None) or None,
                        confidence=0.9,
                    )
                )

        summary = None
        sd = general.get("SummaryDescription")
        if isinstance(sd, dict):
            summary = sd.get("LongSummaryDescription") or sd.get("ShortSummaryDescription")

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
            summary=summary,
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
        params: dict[str, str] = {
            "UserName": self.username or "",
            "Language": self.language,
            "GTIN": ean,
            "Content": "ALL",
        }
        if self.app_key:
            params["app_key"] = self.app_key
        with httpx.Client(timeout=20) as client:
            resp = client.get(self.base_url, params=params)
        if resp.status_code == 403:
            # Produto só no Full Icecat (o Open Icecat não o cobre) — skip gracioso.
            if not self._warned_appkey:
                print(
                    f"[icecat] {ean}: produto só disponível no Full Icecat (fora do Open Icecat). A ignorar.",
                    file=sys.stderr,
                )
                self._warned_appkey = True
            return None
        if resp.status_code in (400, 404):
            # Distingue "utilizador desconhecido" (config errada) de "GTIN não encontrado".
            if "user is unknown" in (resp.text or "").lower() or "user is invalid" in (resp.text or "").lower():
                from .. import observability

                msg = "Icecat: utilizador desconhecido — verifica ICECAT_USERNAME (não é o app_key/Access Token)."
                print(f"[icecat] {msg}", file=sys.stderr)
                observability.capture(
                    RuntimeError(msg), source="icecat", username=self.username, status=resp.status_code
                )
                return None
            return None  # GTIN não encontrado no catálogo acessível (silencioso)
        if resp.status_code == 429 or resp.status_code >= 500:
            raise _Retryable(f"icecat {resp.status_code}")
        resp.raise_for_status()
        body = resp.json()
        if not body.get("data"):
            return None
        return self.parse(body, ean)
