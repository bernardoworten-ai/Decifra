"""Observabilidade (§7): Sentry + logs estruturados (JSON), graceful sem DSN.

Sem SENTRY_DSN, init é no-op e capture() só escreve um log JSON. Nunca quebra.
"""
from __future__ import annotations

import json
import os
import sys
import time

_sentry = None


def init_sentry() -> None:
    """Inicializa o Sentry se SENTRY_DSN existir (e o SDK estiver instalado)."""
    global _sentry
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk

        sentry_sdk.init(
            dsn=dsn,
            traces_sample_rate=0.0,
            environment=os.environ.get("DECIFRA_ENV", "production"),
        )
        _sentry = sentry_sdk
    except Exception:
        _sentry = None


def jlog(event: str, **fields) -> None:
    """Log estruturado em JSON (stderr) — fácil de agregar."""
    record = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": event, **fields}
    print(json.dumps(record, ensure_ascii=False, default=str), file=sys.stderr)


def capture(exc: BaseException, **context) -> None:
    """Regista uma falha (com contexto: fonte, ean, run_id…) no log e no Sentry."""
    jlog("error", error=str(exc), error_type=type(exc).__name__, **context)
    if _sentry is not None:
        try:
            if context:
                _sentry.set_context("decifra", {k: str(v)[:500] for k, v in context.items()})
            _sentry.capture_exception(exc)
        except Exception:
            pass
