"""Utilidades de texto (slugs, normalização leve)."""
from __future__ import annotations

import re
import unicodedata


def slugify(*parts: str | None) -> str:
    """Gera um slug ASCII a partir de uma ou mais partes (marca, modelo…)."""
    raw = " ".join(p for p in parts if p)
    normalized = unicodedata.normalize("NFKD", raw)
    ascii_str = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_str).strip("-").lower()
    return slug or "produto"
