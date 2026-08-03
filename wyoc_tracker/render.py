"""Japanese Markdown report rendering."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any

from .dds import analyze, contract_makeable
from .models import BoardResult, RoomResult, TeamReport
from .pbn import cross_layout, parse_pbn


def _room_dict(room: RoomResult | None) -> dict[str, Any] | None:
    return asdict(room) if room else None


def _contract_parts(contract: str | None) -> tuple[int, str, str] | None:
    if not contract:
        return None
    m = re.match(r"([1-7])\s*(NT|[SHDC])(?:X|XX)?\s*([NESW])", contract.upper().replace(" ", ""))
    if not m:
        return None
    return int(m.group(1)), m.group(2), m.group(3)


def _dds_table(dds: dict) -> str:
    rows = ["| 宣言者 | NT | ♠ | ♥ | ♦ | ♣ |", "|---|---:|---:|---:|---:|---:|"]
    for p, label in (("N", "North"), ("S", "South"), ("E", "East"), ("W", "West")):
        t = dds["tricks"][p]
        rows.append(f"| {label} | {t['NT']} | {t['S']} | {t['H']} | {t['D']} | {t['C']} |")
    return "\n".join(rows)


def _par_text(dds: dict) -> str:
    contracts = ", ".join(c["level"] and f"{c['level']}{c['strain']}{c['declarer']}=" for c in dds["par_contracts"])
    return f"{contracts or 'パー契約なし'}（パースコア: {dds['par_score']}）"


def _comparison(room: RoomResult | None, dds: dict) -> str:
    if not room or not room.contract:
        return "実戦契約は公式記録で確認できず。"
    parts = _contract_parts(room.contract)
    if not parts:
        return f"実戦契約 {room.contract} は解析形式に変換できず。"
    level, strain, declarer = parts
    make = contract_makeable(dds, level, strain, declarer)
    dd_tricks = dds["tricks"][declarer][strain]
    actual = room.tricks
    gap = "不明" if actual is None else str(actual - dd_tricks)
    return f"実戦契約 {room.contract} はダブルダミー上{'メイク可能' if make else 'メイク可能ではない'}。{declarer}の最大トリック数は{dd_tricks}、実戦トリックとの差は{gap}。"


def board_markdown(board: BoardResult) -> tuple[str, dict[str, Any]]:
    deal = parse_pbn(board.pbn)
    dds = analyze(deal, board.dealer, board.vulnerability)
    room_lines = []
    for name, room in (("Open Room", board.open_room), ("Closed Room", board.closed_room)):
        if not room:
            continue
        room_lines.append(f"- **{name}**: 契約 {room.contract or '確認できず'} / リード {room.lead or '確認できず'} / トリック {room.tricks if room.tricks is not None else '確認できず'} / スコア {room.score if room.score is not None else '確認できず'}")
    payload = {"board": board.board, "dealer": board.dealer, "vulnerability": board.vulnerability, "pbn": board.pbn, "open_room": _room_dict(board.open_room), "closed_room": _room_dict(board.closed_room), "imp": board.imp, "dds": dds}
    text = [f"### Board {board.board}", "", "```text", cross_layout(deal, board.board, board.dealer, board.vulnerability), "```", "", *room_lines, "", "#### ダブルダミー解析", "", _dds_table(dds), "", f"- **パー契約／パースコア**: {_par_text(dds)}"]
    if board.open_room:
        text.append(f"- **Open Room比較**: {_comparison(board.open_room, dds)}")
    if board.closed_room:
        text.append(f"- **Closed Room比較**: {_comparison(board.closed_room, dds)}")
    text.extend(["", "実戦のプレイ記録がない場合、ダブルダミーとの差から特定のミスや判断を断定しない。"])
    return "\n".join(text), payload


def team_markdown(report: TeamReport) -> tuple[str, dict[str, Any]]:
    m = report.match
    lines = [f"## {report.team} — Round {report.round_number}", ""]
    if m:
        vp = "確認できず" if m.vp_for is None else f"{m.vp_for:.2f}–{m.vp_against:.2f}"
        imp = "確認できず" if m.imp_for is None else f"{m.imp_for}–{m.imp_against} IMP"
        lines += [f"- 対戦相手: **{m.opponent}**", f"- IMP: **{imp}**", f"- VP: **{vp}**", f"- 順位: {report.rank if report.rank is not None else '確認できず'}（前ラウンド: {report.previous_rank if report.previous_rank is not None else '確認できず'}）", f"- 次ラウンド: {report.next_opponent or '確認できず'} / {report.next_start or '開始時刻確認できず'}", f"- Vugraph: {report.vugraph_status}" + (f" — {report.vugraph_url}" if report.vugraph_url else "") , ""]
    if not report.selected_boards:
        lines.append("注目ボード: 公式ハンドレコードが取得できず。")
    payload_boards = []
    for board in report.selected_boards:
        rendered, payload = board_markdown(board)
        lines += [rendered, ""]
        payload_boards.append(payload)
    payload = asdict(report)
    payload["selected_boards"] = payload_boards
    return "\n".join(lines).rstrip() + "\n", payload


def render_report(reports: list[TeamReport], round_number: int) -> tuple[str, dict[str, Any]]:
    blocks = [f"# WYOC Japan Tracker — Round {round_number}", "", "生成時点で公式サイトから取得できた情報のみを掲載しています。", ""]
    payload: dict[str, Any] = {"round_number": round_number, "teams": []}
    for report in reports:
        block, team_payload = team_markdown(report)
        blocks += [block, ""]
        payload["teams"].append(team_payload)
    return "\n".join(blocks).rstrip() + "\n", payload


def write_outputs(markdown: str, data: dict[str, Any], output_dir: str, round_number: int) -> None:
    from pathlib import Path

    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / f"round-{round_number:02d}.md").write_text(markdown, encoding="utf-8")
    (path / f"round-{round_number:02d}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
