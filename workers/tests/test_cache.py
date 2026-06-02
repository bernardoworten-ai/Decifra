"""Cache / rate-limit best-effort: sem Redis tudo é no-op (offline, sem rede)."""
from __future__ import annotations

import pytest

from decifra_workers import cache


@pytest.fixture(autouse=True)
def _no_redis(monkeypatch):
    monkeypatch.delenv("UPSTASH_REDIS_REST_URL", raising=False)
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN", raising=False)


def test_disabled_without_envs():
    assert cache.enabled() is False


def test_allow_passes_without_redis():
    # Sem Redis o limitador deixa passar — nunca bloqueia o worker.
    assert cache.allow("serpapi", capacity=5, refill_per_sec=1.0) is True


def test_invalidate_is_noop_without_redis():
    cache.invalidate_product("sony-wh-1000xm5")  # não levanta
