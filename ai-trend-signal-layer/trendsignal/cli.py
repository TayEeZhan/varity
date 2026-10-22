"""Command line: python -m trendsignal <command>."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import replace
from pathlib import Path

from trendsignal.jobs import PipelineBusy, load_context, make_digest, run_pipeline, write_ranking_outputs
from trendsignal.output import format_table, to_csv
from trendsignal.queries import feed, source_health


def _print_pipeline(ctx, args: argparse.Namespace) -> None:
    collected, processed = run_pipeline(ctx, force=args.force, only=set(args.source) if args.source else None)
    for outcome in collected.outcomes:
        if outcome.status != "skipped" or args.verbose:
            print(f"  {outcome.source_id:22} {outcome.status:13} new={outcome.new_items:<4} {outcome.message or ''}")
    print(f"collected {collected.new_items} new items ({collected.errors} source errors, ${collected.cost_usd:.4f})")
    _print_process(processed)


def _print_process(processed) -> None:
    print(f"processed: {processed.clustered_items} items clustered into {processed.new_stories} new stories, "
          f"{processed.enriched} labelled ({processed.llm_enriched} by Haiku), {processed.scored} ranked "
          f"({processed.ranked_by_jev} by Jev, {processed.ranked_by_formula} by formula, "
          f"{processed.jev_answers} Jev answers); Haiku ${processed.cost_usd:.4f}, Jev ${processed.jev_cost_usd:.4f}")
    if processed.jev_note:
        print(f"jev: {processed.jev_note}")
    if processed.fallback_reason:
        print(f"haiku: {processed.fallback_reason}")


def _rank(ctx, args: argparse.Namespace) -> int:
    if args.ranker:
        ctx = replace(ctx, settings=replace(ctx.settings, ranker=args.ranker))
    try:
        collected, processed = run_pipeline(ctx, force=args.force, collect=not args.no_collect)
    except PipelineBusy:
        print("another pipeline run is in progress; try again shortly")
        return 1
    document, paths = write_ranking_outputs(ctx, args.out, hours=args.hours)
    rows = document["stories"][: args.limit]
    if args.format == "json":
        print(json.dumps({**document, "stories": rows}, ensure_ascii=False, indent=2))
    elif args.format == "csv":
        print(to_csv(rows), end="")
    else:
        if not args.no_collect:
            print(f"collected {collected.new_items} new items ({collected.errors} source errors)")
        _print_process(processed)
        print(f"\nranked by: {document['ranked_by']} · {len(document['stories'])} stories in the last {args.hours} h"
              f" · wrote {paths['json']} and {paths['csv']}\n")
        print(format_table(rows))
    return 0


def _print_top(ctx, args: argparse.Namespace) -> None:
    for view in feed(ctx.settings, ctx.source_map, since_hours=args.hours)[: args.limit]:
        print(f"{view.importance:5.1f}  {view.tier:12} {view.category:18} {view.title[:80]}")
        print(f"       {' · '.join(view.reasons)}")


def _print_sources(ctx) -> None:
    for row in source_health(ctx.settings, ctx.sources):
        print(f"{row['id']:22} tier {row['tier']}  {row['status']:10} last ok {row['last_ok_at'] or '-':26} "
              f"{(row['last_error'] or '')[:60]}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="trendsignal", description="AI Trend Signal Layer")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create the database")
    rank = sub.add_parser("rank", help="collect, rank, write data/ranked/latest.{json,csv} and print the list")
    rank.add_argument("--no-collect", action="store_true", help="re-rank stored stories without fetching")
    rank.add_argument("--force", action="store_true", help="collect every enabled source now")
    rank.add_argument("--ranker", choices=("formula", "jev"), help="who ranks (default: TRENDSIGNAL_RANKER)")
    rank.add_argument("--limit", type=int, default=20, help="rows to print (files always hold the full list)")
    rank.add_argument("--hours", type=int, default=72, help="only stories first seen in this window")
    rank.add_argument("--out", type=Path, help="output folder (default: data/ranked)")
    rank.add_argument("--format", choices=("table", "json", "csv"), default="table")
    run = sub.add_parser("run", help="collect due sources, then cluster, extract features and rank")
    run.add_argument("--force", action="store_true", help="collect every enabled source now")
    run.add_argument("--source", action="append", help="only this source id (repeatable)")
    digest = sub.add_parser("digest", help="write the daily or weekly brief")
    digest.add_argument("--kind", choices=("daily", "weekly"), default="daily")
    digest.add_argument("--no-llm", action="store_true", help="use the template, not the Editor agent")
    digest.add_argument("--no-deliver", action="store_true", help="do not send to Telegram")
    top = sub.add_parser("top", help="print the current ranking")
    top.add_argument("--limit", type=int, default=15)
    top.add_argument("--hours", type=int, default=72)
    sub.add_parser("sources", help="print source health")
    serve = sub.add_parser("serve", help="run the web app")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    serve.add_argument("--scheduler", action="store_true", help="also run the background schedule")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.command == "serve":
        import uvicorn

        if args.scheduler:
            os.environ["TRENDSIGNAL_SCHEDULER"] = "1"
        uvicorn.run("trendsignal.web.app:create_app", factory=True, host=args.host, port=args.port)
        return 0

    ctx = load_context()
    if args.command == "init":
        print(f"database ready at {ctx.settings.db_path}")
    elif args.command == "rank":
        return _rank(ctx, args)
    elif args.command == "run":
        try:
            _print_pipeline(ctx, args)
        except PipelineBusy:
            print("another pipeline run is in progress; try again shortly")
            return 1
    elif args.command == "digest":
        result = make_digest(ctx, args.kind, use_llm=not args.no_llm, deliver=not args.no_deliver)
        print(result.body)
        print(f"--- generated by {result.generated_by}; verification {result.verification}; "
              f"cost ${result.cost_usd:.4f}; delivered={result.delivered}")
        if result.note:
            print(f"note: {result.note}")
    elif args.command == "top":
        _print_top(ctx, args)
    elif args.command == "sources":
        _print_sources(ctx)
    return 0
