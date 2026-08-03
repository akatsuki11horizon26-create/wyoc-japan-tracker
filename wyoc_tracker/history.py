"""Persistent round snapshots used to preserve historical standings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import TeamReport


def snapshot_path(history_dir: str | Path, round_number: int) -> Path:
    return Path(history_dir) / f"round-{round_number:02d}.json"


def load_snapshot(history_dir: str | Path, round_number: int) -> dict[str, Any] | None:
    path = snapshot_path(history_dir, round_number)
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _team_map(snapshot: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not snapshot:
        return {}
    teams = snapshot.get("teams", [])
    if not isinstance(teams, list):
        return {}
    return {
        str(item.get("team")): item
        for item in teams
        if isinstance(item, dict) and item.get("team")
    }


def apply_history(reports: list[TeamReport], history_dir: str | Path) -> None:
    """Apply saved current/previous ranks without overwriting better live data."""

    if not reports:
        return
    round_number = reports[0].round_number
    current = _team_map(load_snapshot(history_dir, round_number))
    previous = _team_map(load_snapshot(history_dir, round_number - 1)) if round_number > 1 else {}

    for report in reports:
        saved = current.get(report.team)
        if saved and saved.get("rank") is not None:
            report.rank = int(saved["rank"])
            report.rank_as_of = str(saved.get("rank_as_of") or f"保存済みRound {round_number}終了時点")

        previous_saved = previous.get(report.team)
        if report.previous_rank is None and previous_saved and previous_saved.get("rank") is not None:
            report.previous_rank = int(previous_saved["rank"])

        if report.rank is not None and report.previous_rank is not None:
            report.rank_change = report.previous_rank - report.rank


def write_snapshot(reports: list[TeamReport], history_dir: str | Path) -> Path | None:
    """Write a deterministic round snapshot for later rank comparisons."""

    if not reports:
        return None
    round_number = reports[0].round_number
    path = snapshot_path(history_dir, round_number)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = _team_map(load_snapshot(history_dir, round_number))
    teams: list[dict[str, Any]] = []
    for report in sorted(reports, key=lambda item: item.team):
        saved = existing.get(report.team, {})
        rank = saved.get("rank") if saved.get("rank") is not None else report.rank
        rank_as_of = saved.get("rank_as_of") or report.rank_as_of
        teams.append(
            {
                "team": report.team,
                "rank": rank,
                "rank_as_of": rank_as_of,
                "previous_rank": report.previous_rank,
                "rank_change": report.rank_change,
                "opponent": report.match.opponent if report.match else None,
                "imp_for": report.match.imp_for if report.match else None,
                "imp_against": report.match.imp_against if report.match else None,
                "vp_for": report.match.vp_for if report.match else None,
                "vp_against": report.match.vp_against if report.match else None,
            }
        )

    payload = {"round_number": round_number, "teams": teams}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
