"""
check_data.py — Standalone CLI for the data completeness checker.

Audits trawl/tracker workbooks for missing or inconsistent fields and
optionally backfills recoverable salary values without any AI calls.

Usage:
    python check_data.py                            # audit_only, dry run (safe default)
    python check_data.py --mode recover             # local backfill, still dry run
    python check_data.py --mode recover --no-dry-run  # write changes to workbook
    python check_data.py --target trawl_results.xlsx  # override config target list
    python check_data.py --enable                   # override config enabled=false

The script reads config.yaml for all other settings (report paths, backup policy,
refetch toggles, salary defaults, etc.).

Phases:
  Phase A (default): audit_only — produces completeness + recovery reports, no writes.
  Phase B: mode=recover, no-dry-run — writes local salary backfill to workbook.
  Phase C: mode=recover, allow_portal_refetch=true in config — adds network refetch.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

CONFIG_PATH = Path("config.yaml")


def _load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Data completeness checker for trawl/tracker workbooks."
    )
    parser.add_argument(
        "--mode",
        choices=["audit_only", "recover"],
        default=None,
        help="Override data_checker.mode from config (default: use config value).",
    )
    parser.add_argument(
        "--target",
        metavar="FILE",
        action="append",
        dest="targets",
        help="Workbook file to check (can repeat; overrides config targets list).",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        default=False,
        help="Disable dry-run protection and write changes to the workbook.",
    )
    parser.add_argument(
        "--enable",
        action="store_true",
        default=False,
        help="Force-enable checker even if data_checker.enabled=false in config.",
    )
    parser.add_argument(
        "--refetch",
        action="store_true",
        default=False,
        help="Allow portal refetch for unresolved rows (Phase C). "
             "Overrides backfill.allow_portal_refetch in config.",
    )
    return parser.parse_args()


async def _run(config: dict) -> None:
    from core.data_checker import DataChecker

    checker = DataChecker.from_config(config)
    reports = await checker.run()

    if not reports:
        logger.info("No workbooks processed.")
        return

    for report in reports:
        counts = report.outcome_counts
        print(
            f"\n{'=' * 60}\n"
            f"  {Path(report.workbook_path).name}\n"
            f"{'=' * 60}\n"
            f"  Mode     : {report.mode}  |  dry_run={report.dry_run}\n"
            f"  Rows     : {report.total_rows}\n"
            f"  COMPLETE : {counts['COMPLETE']}\n"
            f"  RECOVERED_LOCAL  : {counts['RECOVERED_LOCAL']}\n"
            f"  RECOVERED_REFETCH: {counts['RECOVERED_REFETCH']}\n"
            f"  UNRESOLVED       : {counts['UNRESOLVED']}\n"
            f"  SKIPPED_NO_URL   : {counts['SKIPPED_NO_URL']}\n"
            f"  ERROR_FETCH      : {counts['ERROR_FETCH']}\n"
        )
        if report.field_missing_pct:
            print("  Field missing %:")
            for fname, pct in sorted(
                report.field_missing_pct.items(), key=lambda x: -x[1]
            ):
                print(f"    {fname:<28} {pct:5.1f}%")
        print()


def main() -> None:
    args = _parse_args()
    config = _load_config()

    # Apply CLI overrides on top of config
    dc_cfg = config.setdefault("data_checker", {})

    if args.enable:
        dc_cfg["enabled"] = True

    if not dc_cfg.get("enabled", False):
        logger.error(
            "data_checker.enabled=false in config. "
            "Pass --enable to run anyway, or set enabled=true in config.yaml."
        )
        sys.exit(1)

    if args.mode:
        dc_cfg["mode"] = args.mode

    if args.no_dry_run:
        dc_cfg["dry_run"] = False

    if args.targets:
        dc_cfg["targets"] = args.targets

    if args.refetch:
        dc_cfg.setdefault("backfill", {})["allow_portal_refetch"] = True

    asyncio.run(_run(config))


if __name__ == "__main__":
    main()
