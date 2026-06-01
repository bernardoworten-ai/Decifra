"""Pipelines de ingestão e recompute (blueprint §3).

Scaffold: as assinaturas e o contrato estão definidos; a implementação liga
fontes reais nas fases seguintes. Cada pipeline deve registar a sua execução
em `ingestion_runs` (auditoria + frescura visível ao utilizador).

Regra de ouro: a IA normaliza/explica; nunca é a fonte primária dos números.
Todo o facto persistido leva `source_id` e `confidence`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RunResult:
    status: str  # "ok" | "partial" | "error"
    items: int
    notes: str = ""


def ingest_by_ean(ean: str) -> RunResult:
    """On-demand, cache-first. Em miss: fan-out a EAN API (identidade),
    Icecat/feeds (specs+imagem+preço) e fontes de review (agregados) →
    entity resolution → golden record (products) → cache."""
    raise NotImplementedError("Ligar EAN API + Icecat + entity resolution.")


def refresh_price_live(product_id: str) -> RunResult:
    """Botão "atualizar": Google Shopping (SerpApi/Bright Data) → atualiza
    `offers` deste produto. Pago por consulta — nunca correr globalmente."""
    raise NotImplementedError("Ligar SerpApi/Bright Data.")


def feed_batch() -> RunResult:
    """Cron diário: importa feeds Awin (preço, imagem, deep link de afiliado)
    → atualiza `offers` e imagens em massa, casando por EAN."""
    raise NotImplementedError("Ligar importação de feeds Awin.")


def score_recompute_month(period_key: str) -> RunResult:
    """Cron, dia 10: recalcula `scores` e gera snapshots `rankings`
    (period_type='month') de cada categoria com rankings_enabled."""
    raise NotImplementedError("Recompute mensal + snapshots de ranking.")


def score_recompute_year(period_key: str) -> RunResult:
    """Cron, início de janeiro: snapshots `rankings` (period_type='year')."""
    raise NotImplementedError("Recompute anual.")


def review_refresh() -> RunResult:
    """Cron por popularidade: re-busca agregados de reviews dos produtos mais
    vistos (nota, volume, distribuição, autenticidade) — nunca o texto."""
    raise NotImplementedError("Ligar fontes de review (APIs oficiais + derivados).")
