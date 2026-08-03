"""Command-line entry point for manual and scheduled execution."""

from __future__ import annotations

import argparse
import json
import sys

from . import scraper as scraper_module
from .bbo import configure_scraper
from .history import apply_history, write_snapshot
from .html_report import write_outputs
from .models import BoardResult, RoomResult, TeamReport
from .render import render_report
from .scraper import FetchError, discover_latest_completed_round, fetch_reports


def _room(value):
    return RoomResult(**value) if value else None


def _sample_reports(path: str, round_number: int) -> list[TeamReport]:
    raw = json.loads(open(path, encoding="utf-8").read())
    boards = []
    for item in raw.get("boards", []):
        boards.append(
            BoardResult(
                board=item["board"],
                dealer=item["dealer"],
                vulnerability=item["vulnerability"],
                pbn=item["pbn"],
                imp=item.get("imp"),
                open_room=_room(item.get("open_room")),
                closed_room=_room(item.get("closed_room")),
            )
        )
    return [TeamReport(team=raw.get("team", "SAMPLE"), round_number=round_number, selected_boards=boards)]


def _parse_round(value: str) -> int | None:
    if value.lower() == "auto":
        return None
    try:
        round_number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--round must be an integer or 'auto'") from exc
    if not 1 <= round_number <= 200:
        raise argparse.ArgumentTypeError("--round must be between 1 and 200")
    return round_number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a WYOC Japan DDS report")
    parser.add_argument("--round", default="auto", help="round number or 'auto'")
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument("--cache-dir", default="data/cache")
    parser.add_argument("--history-dir", default="data/history")
    parser.add_argument("--no-cache", action="store_true", help="disable the HTML cache for this run")
    parser.add_argument("--input", help="normalized JSON fixture; skips WBF HTTP retrieval")
    args = parser.parse_args(argv)

    configure_scraper(scraper_module)

    try:
        requested = _parse_round(args.round)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    try:
        if args.input:
            if requested is None:
                parser.error("--input requires an explicit numeric --round")
            round_number = requested
            latest = requested
            reports = _sample_reports(args.input, round_number)
        else:
            cache_dir = None if args.no_cache else args.cache_dir
            if requested is None:
                latest = discover_latest_completed_round(cache_dir=cache_dir)
                round_number = latest
            else:
                # A manually requested round is fetched directly. The round's
                # own score, board and hand pages are the source of truth; a
                # stale tournament index must not block an already published
                # round. fetch_reports still raises FetchError when required
                # official data cannot be retrieved.
                round_number = requested
                latest = requested
            reports = fetch_reports(
                round_number,
                cache_dir=cache_dir,
                latest_completed_round=latest,
            )

        apply_history(reports, args.history_dir)
        markdown, payload = render_report(reports, round_number)
        write_outputs(markdown, payload, args.output_dir, round_number)
        write_snapshot(reports, args.history_dir)
        print(
            json.dumps(
                {
                    "round": round_number,
                    "latest_completed_round": latest,
                    "teams": [report.team for report in reports],
                    "output_dir": args.output_dir,
                    "history_dir": args.history_dir,
                    "formats": ["markdown", "json", "html"],
                },
                ensure_ascii=False,
            )
        )
        return 0
    except (FetchError, RuntimeError) as exc:
        print(f"生成失敗: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
