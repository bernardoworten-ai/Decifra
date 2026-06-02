"""Interface comum a todos os connectors de fonte."""
from __future__ import annotations

import abc

from ..models import RawRecord


class SourceConnector(abc.ABC):
    """Contrato de uma fonte. Cada connector regista-se em `sources` (por nome)
    e devolve `RawRecord`s normalizados, anotados com a sua confiança."""

    name: str
    kind: str  # identity | specs | offers | reviews | expert
    trust_weight: float = 0.5
    base_url: str | None = None

    @abc.abstractmethod
    def configured(self) -> bool:
        """True se o connector tem o que precisa para correr (creds/URL)."""

    def fetch_by_ean(self, ean: str) -> RawRecord | None:  # noqa: ARG002
        """Identidade/specs por EAN. None se não encontrar."""
        raise NotImplementedError(f"{self.name} não suporta fetch_by_ean")
