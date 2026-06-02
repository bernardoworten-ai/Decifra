"""Camada de IA (Claude/Haiku) — explicação e normalização, ancorada em factos.

Regra de ouro (blueprint §1): a IA explica/normaliza/raciocina; NUNCA é a fonte
primária dos números. Aqui só gera texto (resumos) a partir de factos já
recolhidos de fontes reais — instruída a não inventar.
"""
from __future__ import annotations

import os

from .models import RawRecord

DEFAULT_MODEL = "claude-haiku-4-5-20251001"


def _client():
    """Cria o cliente Anthropic se a chave existir (e o SDK estiver instalado)."""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        from anthropic import Anthropic
    except ImportError:
        return None
    return Anthropic(api_key=key)


def _model() -> str:
    return os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL


def summarize_product(record: RawRecord, *, max_specs: int = 12) -> str | None:
    """Resumo curto (1–2 frases, PT-PT) a partir dos factos do produto.

    Devolve None se a IA não estiver configurada ou falhar — nunca levanta.
    """
    client = _client()
    if client is None:
        return None

    facts: list[str] = []
    if record.brand:
        facts.append(f"Marca: {record.brand}")
    if record.name:
        facts.append(f"Nome: {record.name}")
    for spec in record.specs[:max_specs]:
        value = spec.value_text or (str(spec.value_num) if spec.value_num is not None else None)
        if value:
            facts.append(f"- {spec.key}: {value}{(' ' + spec.unit) if spec.unit else ''}")
    if not facts:
        return None

    prompt = (
        "És um redator do DECIFRA, um comparador de produtos. Escreve um resumo "
        "objetivo de 1 a 2 frases, em português de Portugal, APENAS com base nos "
        "factos abaixo. NÃO inventes especificações, números nem opiniões; não uses "
        "linguagem de marketing. Se os factos forem escassos, escreve algo curto e neutro.\n\n"
        "Factos:\n" + "\n".join(facts)
    )
    try:
        msg = client.messages.create(
            model=_model(),
            max_tokens=180,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in msg.content if block.type == "text").strip()
        return text or None
    except Exception:
        return None  # IA é best-effort; nunca quebra a ingestão


def rank_rationale(
    product_name: str, criterion_label: str, metric_text: str, rank: int
) -> str | None:
    """Frase curta (PT-PT) a explicar a posição do produto no ranking do critério.

    Ancorada no dado fornecido (metric_text). Devolve None se IA indisponível/falhar.
    """
    client = _client()
    if client is None:
        return None
    prompt = (
        "És um redator do DECIFRA, um comparador de produtos. Numa única frase curta "
        "(português de Portugal, máx. ~18 palavras), explica porque este produto está na "
        f"posição {rank} deste critério, USANDO apenas o dado fornecido. Se a posição não "
        "for 1, NÃO digas que é o melhor/maior/mais alto. NÃO inventes números nem opiniões; "
        "não uses linguagem de marketing.\n\n"
        f"Produto: {product_name}\nCritério: {criterion_label}\nPosição: {rank}\nDado: {metric_text}"
    )
    try:
        msg = client.messages.create(
            model=_model(),
            max_tokens=90,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in msg.content if block.type == "text").strip()
        return text or None
    except Exception:
        return None
