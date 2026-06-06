"""Camada de IA (Claude/Haiku) — explicação e normalização, ancorada em factos.

Regra de ouro (blueprint §1): a IA explica/normaliza/raciocina; NUNCA é a fonte
primária dos números. Aqui só gera texto (resumos) a partir de factos já
recolhidos de fontes reais — instruída a não inventar.
"""
from __future__ import annotations

import json
import os
import re

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


def choose_discriminant_attributes(category_name: str, attributes: list[dict]) -> list[str]:
    """Pede ao Haiku as chaves de atributos mais discriminantes para a categoria.

    `attributes`: [{key, label, data_type, values:[...]}]. Devolve lista de keys
    (vazia se IA indisponível/falhar — o chamador aplica fallback por variância).
    """
    client = _client()
    if client is None:
        return []
    lines = [
        f"- {a['key']} ({a['label']}, {a['data_type']}): valores={a['values'][:6]}"
        for a in attributes
    ]
    prompt = (
        f"És o DECIFRA, um comparador de produtos. Para a categoria '{category_name}', escolhe "
        "os 1 a 5 atributos MAIS discriminantes para ajudar alguém a escolher — prioriza os que "
        "VARIAM entre produtos e são decisivos na compra; ignora os que têm sempre o mesmo valor. "
        'Responde APENAS com um array JSON das chaves, ex.: ["autonomia","sistema"].\n\n'
        "Atributos:\n" + "\n".join(lines)
    )
    try:
        msg = client.messages.create(
            model=_model(),
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in msg.content if block.type == "text")
        match = re.search(r"\[.*\]", text, re.S)
        if not match:
            return []
        arr = json.loads(match.group(0))
        return [str(x) for x in arr if isinstance(x, str)]
    except Exception:
        return []


def review_authenticity(signals: dict) -> tuple[float, str] | None:
    """Deteta autenticidade (0-1) + rótulo a partir de SINAIS agregados (nunca do
    texto). Preenche o gap do Fakespot/ReviewMeta. None se a IA estiver off."""
    client = _client()
    if client is None:
        return None
    prompt = (
        "És o detetor de autenticidade de reviews do DECIFRA (no espírito do Fakespot/"
        "ReviewMeta). Com base APENAS nestes sinais agregados (nota, volume, distribuição "
        "por estrelas, recência) — NUNCA no texto das reviews — estima a probabilidade de "
        "as reviews serem autênticas. Sinais de alerta: distribuição muito polarizada (só "
        "5★), volume anómalo, picos recentes. Responde só JSON "
        '{"score": 0..1, "label": "alta|média|baixa"}.\n\nSinais: '
        + json.dumps(signals, ensure_ascii=False)
    )
    try:
        msg = client.messages.create(
            model=_model(), max_tokens=120, messages=[{"role": "user", "content": prompt}]
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        data = json.loads(match.group(0))
        score = max(0.0, min(1.0, float(data["score"])))
        return score, str(data.get("label") or "")
    except Exception:
        return None


def review_themes_summary(theme_tokens: list[tuple[str, str]]) -> tuple[list[dict], str] | None:
    """A partir de temas JÁ DERIVADOS (pros/cons/keywords — não do texto), agrupa em
    review_themes (tema, sentimento, frequência) + resumo próprio PT-PT. None se IA off."""
    client = _client()
    if client is None or not theme_tokens:
        return None
    listed = "; ".join(f"{t} ({pol})" for t, pol in theme_tokens[:24])
    prompt = (
        "És redator do DECIFRA. A partir destes TEMAS já derivados (pros/cons; NÃO é o texto "
        "das reviews), agrupa em 3 a 6 temas concisos e escreve um resumo PRÓPRIO de 1-2 frases "
        "(português de Portugal), sem inventar e sem copiar frases. Responde só JSON: "
        '{"themes": [{"theme": "", "polarity": "positivo|negativo|misto", "frequency": int}], '
        '"summary": ""}.\n\nTemas: ' + listed
    )
    try:
        msg = client.messages.create(
            model=_model(), max_tokens=400, messages=[{"role": "user", "content": prompt}]
        )
        text = "".join(b.text for b in msg.content if b.type == "text")
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        data = json.loads(match.group(0))
        themes = [
            {
                "theme": str(t.get("theme", "")).strip()[:120],
                "polarity": t.get("polarity", "misto"),
                "frequency": int(t.get("frequency") or 1),
            }
            for t in (data.get("themes") or [])
            if t.get("theme")
        ]
        return themes, str(data.get("summary") or "")
    except Exception:
        return None
