"""Cache / rate-limit best-effort em Upstash Redis (REST), partilhado com a web.

Sem UPSTASH_REDIS_REST_URL/TOKEN tudo é no-op (não quebra). Usa o mesmo esquema
de chaves da web (decifra:idx:product:<slug>) para invalidação cross-language.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx


def _conf() -> tuple[str | None, str | None]:
    return os.environ.get("UPSTASH_REDIS_REST_URL"), os.environ.get("UPSTASH_REDIS_REST_TOKEN")


def enabled() -> bool:
    url, token = _conf()
    return bool(url and token)


def _cmd(*args: Any) -> Any:
    """Executa um comando Redis via REST. Devolve o `result` ou None (best-effort)."""
    url, token = _conf()
    if not (url and token):
        return None
    try:
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {token}"},
            json=[str(a) for a in args],
            timeout=5,
        )
        resp.raise_for_status()
        return resp.json().get("result")
    except Exception:
        return None


def invalidate_product(slug: str) -> None:
    """Apaga as chaves de cache de lookup associadas a um produto (preço/score mudaram)."""
    if not enabled() or not slug:
        return
    idx = f"decifra:idx:product:{slug}"
    members = _cmd("SMEMBERS", idx) or []
    if members:
        _cmd("DEL", *members)
    _cmd("DEL", idx)


def allow(source: str, capacity: float, refill_per_sec: float, cost: float = 1.0) -> bool:
    """Token bucket best-effort por fonte (throttle das APIs pagas — gancho p/ P4).

    Sem Redis devolve sempre True. Não-atómico de propósito (suficiente para um
    worker; troca por EVAL/Lua se precisares de exatidão sob concorrência)."""
    if not enabled():
        return True
    key = f"decifra:rl:{source}"
    now = time.time()
    raw = _cmd("GET", key)
    try:
        data = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        data = None
    tokens = float(data["tokens"]) if data else capacity
    ts = float(data["ts"]) if data else now
    tokens = min(capacity, tokens + (now - ts) * refill_per_sec)
    allowed = tokens >= cost
    if allowed:
        tokens -= cost
    ttl = int(capacity / refill_per_sec) + 60 if refill_per_sec > 0 else 3600
    _cmd("SET", key, json.dumps({"tokens": tokens, "ts": now}), "EX", ttl)
    return allowed
