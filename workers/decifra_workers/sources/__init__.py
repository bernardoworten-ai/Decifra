"""Connectors de fontes externas (identidade, specs, ofertas, reviews)."""
from __future__ import annotations

from ..config import Settings
from .awin import AwinFeedConnector
from .base import SourceConnector
from .icecat import IcecatConnector
from .upcitemdb import UpcItemDbConnector

__all__ = [
    "SourceConnector",
    "UpcItemDbConnector",
    "IcecatConnector",
    "AwinFeedConnector",
    "build_connectors",
]


def build_connectors(settings: Settings) -> list[SourceConnector]:
    """Instancia os connectors a partir da configuração disponível."""
    return [
        UpcItemDbConnector(api_key=settings.go_upc_api_key),
        IcecatConnector(username=settings.icecat_username),
        AwinFeedConnector(feed_url=settings.awin_feed_url),
    ]
