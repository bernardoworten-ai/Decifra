"""CLI dos workers.

  python -m decifra_workers ingest-ean 049000028911 [--dry-run]
  python -m decifra_workers feed-batch [--limit N]
"""
from __future__ import annotations

import argparse
import sys

from . import pipelines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="decifra_workers", description="Workers de ingestão DECIFRA")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ean = sub.add_parser("ingest-ean", help="Ingestão on-demand por EAN")
    p_ean.add_argument("ean")
    p_ean.add_argument("--dry-run", action="store_true", help="Não escreve na BD; só mostra")

    p_feed = sub.add_parser("feed-batch", help="Importa feed Awin (ofertas)")
    p_feed.add_argument("--limit", type=int, default=None, help="Máx. de linhas a processar")

    p_rank = sub.add_parser("score-recompute", help="Gera snapshots de rankings (mês)")
    p_rank.add_argument("--period", default=None, help="YYYY-MM (default: mês atual)")
    p_rank.add_argument("--no-ai", action="store_true", help="Não usar IA no rationale")

    p_fq = sub.add_parser("finder-questions", help="IA escolhe perguntas discriminantes (cauda longa)")
    p_fq.add_argument("--category", default=None, help="slug da categoria (default: todas as que faltam)")
    p_fq.add_argument("--no-ai", action="store_true", help="Só fallback por variância")

    sub.add_parser("check-alerts", help="Verifica alertas de preço dos favoritos")

    args = parser.parse_args(argv)

    if args.cmd == "ingest-ean":
        res = pipelines.ingest_by_ean(args.ean, dry_run=args.dry_run)
    elif args.cmd == "feed-batch":
        res = pipelines.feed_batch(limit=args.limit)
    elif args.cmd == "score-recompute":
        res = pipelines.score_recompute_month(period_key=args.period, use_ai=not args.no_ai)
    elif args.cmd == "finder-questions":
        res = pipelines.generate_finder_questions(category_slug=args.category, use_ai=not args.no_ai)
    elif args.cmd == "check-alerts":
        res = pipelines.check_price_alerts()
    else:  # pragma: no cover
        parser.error("comando desconhecido")

    print(f"[{res.status}] {res.notes}")
    return 0 if res.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
