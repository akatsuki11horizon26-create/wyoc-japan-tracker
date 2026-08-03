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
    match = re.match(r"([1-7])\s*(NT|[SHDC])(?:X|XX)?\s*([NESW])", contract.upper().replace(" ", ""))
    if not match:
        return None
    return int(match.group(1)), match.group(2), match.group(3)


def _dds_table(dds: dict) -> str:
    rows = ["| 宣言者 | NT | ♠ | ♥ | ♦ | ♣ |", "|---|---:|---:|---:|---:|---:|"]
    for player, label in (("N", "North"), ("S", "South"), ("E", "East"), ("W", "West")):
        tricks = dds["tricks"][player]
        rows.append(f"| {label} | {tricks['NT']} | {tricks['S']} | {tricks['H']} | {tricks['D']} | {tricks['C']} |")
    return "\n".join(rows)


def _par_text(dds: dict) -> str:
    contracts = ", ".join(
        f"{contract['level']}{contract['strain']}{contract['declarer']}="
        for contract in dds["par_contracts"]
        if contract["level"]
    )
    return f"{contracts or 'パー契約なし'}（パースコア: {dds['par_score']}）"


def _comparison(room: RoomResult | None, dds: dict) -> str:
    if not room or not room.contract:
        return "実戦契約は公式記録で確認できず。"
    parts = _contract_parts(room.contract)
    if not parts:
        return f"実戦契約 {room.contract} は解析形式に変換できず。"
    level, strain, declarer = parts
    makeable = contract_makeable(dds, level, strain, declarer)
    dd_tricks = dds["tricks"][declarer][strain]
    gap = "不明" if room.tricks is None else str(room.tricks - dd_tricks)
    return f"実戦契約 {room.contract} はダブルダミー上{'メイク可能' if makeable else 'メイク可能ではない'}。{declarer}の最大トリック数は{dd_tricks}、実戦トリックとの差は{gap}。"


def board_markdown(board: BoardResult) -> tuple[str, dict[str, Any]]:
    deal = parse_pbn(board.pbn)
    dds = analyze(deal, board.dealer, board.vulnerability)
    swing = "IMP確認できず" if board.imp is None else f"日本に{board.imp:+d} IMP"
    room_lines = [f"- **スイング**: {swing}"]
    for name, room in (("Open Room", board.open_room), ("Closed Room", board.closed_room)):
        if room:
            room_lines.append(
                f"- **{name}**: 契約 {room.contract or '確認できず'} / リード {room.lead or '確認できず'} / "
                f"トリック {room.tricks if room.tricks is not None else '確認できず'} / "
                f"スコア {room.score if room.score is not None else '確認できず'}"
            )
    payload = {
        "board": board.board,
        "dealer": board.dealer,
        "vulnerability": board.vulnerability,
        "pbn": board.pbn,
        "open_room": _room_dict(board.open_room),
        "closed_room": _room_dict(board.closed_room),
        "imp": board.imp,
        "dds": dds,
    }
    text = [
        f"### Board {board.board} — {swing}",
        "",
        "```text",
        cross_layout(deal, board.board, board.dealer, board.vulnerability),
        "```",
        "",
        *room_lines,
        "",
        "#### ダブルダミー解析",
        "",
        _dds_table(dds),
        "",
        f"- **パー契約／パースコア**: {_par_text(dds)}",
    ]
    if board.open_room:
        text.append(f"- **Open Room比較**: {_comparison(board.open_room, dds)}")
    if board.closed_room:
        text.append(f"- **Closed Room比較**: {_comparison(board.closed_room, dds)}")
    text.extend(["", "実戦のプレイ記録がない場合、ダブルダミーとの差から特定のミスや判断を断定しない。"])
    return "\n".join(text), payload


def team_markdown(report: TeamReport) -> tuple[str, dict[str, Any]]:
    match = report.match
    lines = [f"## {report.team} — Round {report.round_number}", ""]
    if match:
        vp = "確認できず" if match.vp_for is None else f"{match.vp_for:.2f}–{match.vp_against:.2f}"
        imp = "確認できず" if match.imp_for is None else f"{match.imp_for}–{match.imp_against} IMP"
        rank_label = report.rank_as_of or "取得時点"
        lines += [
            f"- 対戦相手: **{match.opponent}**",
            f"- IMP: **{imp}**",
            f"- VP: **{vp}**",
            f"- 順位（{rank_label}）: {report.rank if report.rank is not None else '確認できず'}",
            f"- 次ラウンド: {report.next_opponent or '確認できず'} / {report.next_start or '開始時刻確認できず'}",
            f"- Vugraph: {report.vugraph_status}" + (f" — {report.vugraph_url}" if report.vugraph_url else ""),
            "",
        ]
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
    blocks = [
        f"# WYOC Japan Tracker — Round {round_number}",
        "",
        "生成時点で公式サイトから取得できた情報のみを掲載しています。順位はラウンド終了時点ではなく、明記した取得時点の公式順位です。",
        "",
    ]
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
