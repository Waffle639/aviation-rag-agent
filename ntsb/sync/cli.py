"""Command-line entrypoint for the NTSB PostgreSQL index."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from ntsb.sync.errors import NTSBError
from ntsb.sync.service import NTSBSyncService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synchronize the NTSB aviation index.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("backfill", "incremental"):
        command = subparsers.add_parser(name)
        command.add_argument(
            "--summary-only",
            action="store_true",
            help="Store only endpoint summaries. Not recommended for rankings or cause questions.",
        )
        if name == "backfill":
            command.add_argument(
                "--refresh-existing",
                action="store_true",
                help="Rehydrate and upsert cases that are already present. Default is to skip them quickly.",
            )
    subparsers.add_parser("status")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    args = _parser().parse_args(argv)
    service = NTSBSyncService()
    try:
        if args.command == "backfill":
            stats = service.run_backfill(
                hydrate_details=not args.summary_only,
                refresh_existing=args.refresh_existing,
            )
        elif args.command == "incremental":
            stats = service.run_incremental(hydrate_details=not args.summary_only)
        else:
            print(json.dumps(service.status(), indent=2))
            return 0
        if stats is not None:
            print(
                "NTSB sync completed: "
                f"pages={stats.pages} records={stats.records_received} "
                f"upserted={stats.cases_upserted} details={stats.details_fetched} "
                f"skipped_existing={stats.skipped_existing} "
                f"rejected={stats.rejected}"
            )
        return 0
    except NTSBError as exc:
        print(f"NTSB sync failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
