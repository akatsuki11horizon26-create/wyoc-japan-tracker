"""Command-line entry point for manual and Actions execution."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields

from .models import BoardResult, RoomResult, TeamReport
from .render import render_report, write_outputs
from .scraper import FetchError, fetch_reports


def _room(value):
    return RoomResult(**value) if value else None


def _sample_reports(path: str, round_number: int) -> list[TeamReport]:
    """Load a normalized fixture, useful for local tests and offline reruns."""
    raw = json.loads(open(path, encoding="utf-8").read())
    boards = []
    for item in raw.get("boards", []):
        boards.append(BoardResult(board=item["board"], dealer=item["dealer"], vulnerability=item["vulnerability"], pbn=item["pbn"], imp=item.get("imp"), open_room=_room(item.get("open_room")), closed_room=_room(item.get("closed_room"))))
    return [TeamReport(team=raw.get("team", "SAMPLE"), round_number=round_number, selected_boards=boards)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a WYOC Japan DDS report")
    parser.add_argument("--round", type=int, required=True, dest="round_number")
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument("--cache-dir", default="data/cache")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--input", help="normalized JSON fixture; skips WBF HTTP retrieval")
    args = parser.parse_args(argv)
    if not 1 <= args.round_number <= 200:
        parser.error("--round must be between 1 and 200")
    try:
        reports = _sample_reports(args.input, args.round_number) if args.input else fetch_reports(args.round_number, cache_dir=None if args.no_cache else args.cache_dir)
        markdown, payload = render_report(reports, args.round_number)
        write_outputs(markdown, payload, args.output_dir, args.round_number)
        print(json.dumps({"round": args.round_number, "teams": [r.team for r in reports], "output_dir": args.output_dir}, ensure_ascii=False))
        return 0
    except FetchError as exc:
        print(f"取得失敗: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
