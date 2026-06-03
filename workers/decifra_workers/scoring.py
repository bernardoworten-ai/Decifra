"""Matemática do DECIFRA Score (blueprint §4) — funções puras, testáveis.

Espelha web/src/lib/score.ts (a metodologia é a mesma). É a fonte de verdade do
recompute (workers): deriva os 4 sub-scores de SINAIS reais, com renormalização
quando faltam, e nunca inventa números (§1). Sem testes físicos (§0).
"""
from __future__ import annotations

import math

# Pesos por defeito + por categoria (o que importa varia: build pesa mais num
# eletrodoméstico/SSD; especialistas+users em áudio).
DEFAULT_WEIGHTS = {"expert": 0.35, "users": 0.30, "material": 0.20, "value": 0.15}
CATEGORY_WEIGHTS: dict[str, dict[str, float]] = {
    "auscultadores": {"expert": 0.35, "users": 0.30, "material": 0.20, "value": 0.15},
    "ssd": {"expert": 0.25, "users": 0.25, "material": 0.30, "value": 0.20},
    "smartwatches": {"expert": 0.30, "users": 0.30, "material": 0.25, "value": 0.15},
}


def weights_for(category_slug: str | None) -> dict[str, float]:
    return CATEGORY_WEIGHTS.get(category_slug or "", DEFAULT_WEIGHTS)


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def combine_overall(subs: dict[str, float | None], weights: dict[str, float]) -> float | None:
    """overall 0-100, renormalizando os pesos sobre os sub-scores presentes."""
    parts = [(subs[k], weights[k]) for k in ("expert", "users", "material", "value") if subs.get(k) is not None]
    total_w = sum(w for _, w in parts)
    if total_w == 0:
        return None
    return round(sum(v * w for v, w in parts) / total_w, 1)


def confidence_from_sources(source_count: int, avg_trust: float) -> float:
    """0-1, função do nº e do trust_weight médio das fontes (satura suavemente)."""
    if source_count <= 0:
        return 0.0
    volume = 1 - math.exp(-0.55 * source_count)
    return round(clamp01(volume * (0.5 + 0.5 * clamp01(avg_trust))), 2)


def aggregate_expert(signals: list[tuple[float, float]]) -> float | None:
    """sub_expert: média (0-100) dos veredictos de especialistas, ponderada por trust."""
    valid = [(v, t) for v, t in signals if v is not None]
    if not valid:
        return None
    total_t = sum(t for _, t in valid) or 1.0
    return round(sum(v * t for v, t in valid) / total_t, 1)


def aggregate_users(reviews: list[tuple[float | None, int]]) -> float | None:
    """sub_users: nota ajustada (0-5 → 0-100), ponderada por volume de reviews."""
    valid = [(r, c) for r, c in reviews if r is not None and c > 0]
    if not valid:
        return None
    total = sum(c for _, c in valid)
    return round(sum(r * 20.0 * c for r, c in valid) / total, 1)


def _theme_factor(freq: float) -> float:
    return 0.0 if not freq else min(10.0, 3.0 * math.log10(1 + freq))


def material_score(
    warranty_years: float | None,
    tbw_tb: float | None,
    has_certification: bool,
    theme_pos_freq: float,
    theme_neg_freq: float,
) -> float | None:
    """sub_material: build/materiais/certificações/garantia/durabilidade → 0-100.

    Devolve None se não houver QUALQUER sinal de material (renormaliza)."""
    has_input = (
        warranty_years is not None
        or tbw_tb is not None
        or has_certification
        or theme_pos_freq
        or theme_neg_freq
    )
    if not has_input:
        return None
    base = 60.0
    if warranty_years is not None:
        base += min(warranty_years, 5) / 5 * 15  # garantia → até +15
    if tbw_tb is not None:
        base += min(tbw_tb / 2000.0, 1.0) * 10  # resistência (TBW) → até +10
    if has_certification:
        base += 10  # IP / MIL-STD
    base += _theme_factor(theme_pos_freq) - _theme_factor(theme_neg_freq)
    return round(_clamp(base), 1)


def value_scores(items: list[tuple[str, float | None, float | None]]) -> dict[str, float]:
    """sub_value 0-100, relativo à categoria: qualidade-base por € normalizada.

    items: [(product_id, base_quality, price)]. Mapeia para [50, 100] (o pior em
    relação qualidade/preço não fica a zero). Caso degenerado (1 produto) → 75."""
    ratios = {pid: q / price for pid, q, price in items if q is not None and price and price > 0}
    if not ratios:
        return {}
    lo, hi = min(ratios.values()), max(ratios.values())
    out: dict[str, float] = {}
    for pid, r in ratios.items():
        out[pid] = 75.0 if hi == lo else round(50.0 + (r - lo) / (hi - lo) * 50.0, 1)
    return out


def adjusted_rating(raw: float | None, authenticity: float | None) -> float | None:
    """Nota ajustada por autenticidade (estilo ReviewMeta): baixa autenticidade
    puxa a nota para o neutro (3,0). Sem autenticidade ⇒ devolve a nota crua."""
    if raw is None:
        return None
    if authenticity is None:
        return round(raw, 2)
    factor = 0.7 + 0.3 * clamp01(authenticity)
    return round(max(0.0, min(5.0, 3.0 + (raw - 3.0) * factor)), 2)
