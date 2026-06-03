"""CLI dos workers (invocada pelos crons do §3 e on-demand).

  python -m decifra_workers feed-batch
  python -m decifra_workers score-recompute --period month
  python -m decifra_workers review-refresh-popular --limit 20
"""
from __future__ import annotations

import argparse
import sys

from . import observability, pipelines


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="decifra_workers", description="Workers de ingestão DECIFRA")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ean = sub.add_parser("ingest-ean", help="Ingestão on-demand por EAN")
    p_ean.add_argument("ean")
    p_ean.add_argument("--dry-run", action="store_true", help="Não escreve na BD; só mostra")

    p_feed = sub.add_parser("feed-batch", help="Importa feed Awin (ofertas) — cron diário")
    p_feed.add_argument("--limit", type=int, default=None, help="Máx. de linhas a processar")

    p_rank = sub.add_parser("score-recompute", help="Recalcula scores + congela rankings (§3/§4)")
    p_rank.add_argument("--period", choices=["month", "year"], default="month")
    p_rank.add_argument("--period-key", default=None, help="ex.: 2026-06 ou 2026 (default: atual)")
    p_rank.add_argument("--no-ai", action="store_true", help="Sem IA no rationale")

    p_fq = sub.add_parser("finder-questions", help="IA escolhe perguntas discriminantes (cauda longa)")
    p_fq.add_argument("--category", default=None, help="slug da categoria (default: todas as que faltam)")
    p_fq.add_argument("--no-ai", action="store_true", help="Só fallback por variância")

    sub.add_parser("check-alerts", help="Verifica alertas de preço dos favoritos")

    p_rev = sub.add_parser("review-refresh", help="Métricas de reviews por loja (sem texto, §5)")
    p_rev.add_argument("slug", help="slug do produto")
    p_rev.add_argument("--url", default=None, help="página pública com schema.org aggregateRating")
    p_rev.add_argument("--source", default=None, help="nome da fonte (ex.: trustpilot, google)")
    p_rev.add_argument("--no-ai", action="store_true", help="Sem IA (autenticidade/temas)")

    p_pop = sub.add_parser("review-refresh-popular", help="Reviews por popularidade — cron")
    p_pop.add_argument("--limit", type=int, default=20, help="nº de produtos mais populares")
    p_pop.add_argument("--no-ai", action="store_true", help="Sem IA (autenticidade/temas)")

    p_price = sub.add_parser("refresh-price", help="Preço live on-demand (§3) — NUNCA em cron (§10)")
    p_price.add_argument("slug", help="slug do produto")

    p_cons = sub.add_parser("consolidate", help="Consolidação real: ingere vários EAN + recompute")
    p_cons.add_argument("eans", nargs="+", help="Um ou mais EAN/UPC")
    p_cons.add_argument("--no-ai", action="store_true", help="Sem IA (resumos/rationale)")
    return parser


def _dispatch(args: argparse.Namespace):
    if args.cmd == "ingest-ean":
        return pipelines.ingest_by_ean(args.ean, dry_run=args.dry_run)
    if args.cmd == "feed-batch":
        return pipelines.feed_batch(limit=args.limit)
    if args.cmd == "score-recompute":
        return pipelines.score_recompute(args.period, args.period_key, use_ai=not args.no_ai)
    if args.cmd == "finder-questions":
        return pipelines.generate_finder_questions(category_slug=args.category, use_ai=not args.no_ai)
    if args.cmd == "check-alerts":
        return pipelines.check_price_alerts()
    if args.cmd == "review-refresh":
        return pipelines.review_refresh(args.slug, url=args.url, source_name=args.source, use_ai=not args.no_ai)
    if args.cmd == "review-refresh-popular":
        return pipelines.review_refresh_popular(limit=args.limit, use_ai=not args.no_ai)
    if args.cmd == "refresh-price":
        return pipelines.refresh_price(args.slug)
    if args.cmd == "consolidate":
        return pipelines.consolidate(args.eans, use_ai=not args.no_ai)
    raise SystemExit(f"comando desconhecido: {args.cmd}")


def _record_job_error(cmd: str, exc: BaseException) -> None:
    """Alerta mínimo (§7): job falhado fica em ingestion_runs com status 'error'."""
    try:
        from . import db
        from .config import Settings

        conn = db.connect(Settings.from_env().database_url)
        try:
            run_id = db.start_run(conn, None, cmd[:24])
            db.finish_run(conn, run_id, "error", 0, str(exc)[:480])
        finally:
            conn.close()
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    observability.init_sentry()
    args = _build_parser().parse_args(argv)
    observability.jlog("job_start", command=args.cmd)
    try:
        res = _dispatch(args)
    except Exception as exc:  # noqa: BLE001 — fronteira do job: regista e sai
        observability.capture(exc, command=args.cmd)
        _record_job_error(args.cmd, exc)
        print(f"[error] {args.cmd}: {exc}", file=sys.stderr)
        return 1
    observability.jlog("job_done", command=args.cmd, status=res.status, items=res.items)
    print(f"[{res.status}] {res.notes}")
    return 0 if res.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
