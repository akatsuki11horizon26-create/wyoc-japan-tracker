"""Japanese Markdown and JSON report rendering."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from .dds import (
    analyze,
    contract_makeable,
    opening_lead_analysis,
    parse_contract,
)
from .models import BoardResult, RoomResult, TeamReport
from .pbn import PLAYER_NAMES, SUIT_SYMBOLS, cross_layout, parse_pbn

LEAD_RULE_LABELS = {
    "top_of_honor": "Top of Honor（連続オナー）",
    "third_from_even": "3rd（偶数枚）",
    "lowest_from_odd": "lowest（奇数枚）",
    "fourth_best": "4th best（オナーあり）",
    "top_of_nothing": "Top of Nothing（オナーなし）",
    "second_best": "2nd best（オナーなし）",
    "lowest_from_three": "3枚からlowest（4th best不可）",
    "top_of_doubleton": "ダブルトンのトップ",
    "singleton": "シングルトン",
    "void": "ボイド",
}
STRAIN_SYMBOLS = {"NT": "NT", "S": "♠", "H": "♥", "D": "♦", "C": "♣"}


def _room_dict(room: RoomResult | None) -> dict[str, Any] | None:
    return asdict(room) if room else None


def _dds_table(dds: dict) -> str:
    rows = [
        "| 宣言者 | NT | ♠ | ♥ | ♦ | ♣ |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for player, label in (
        ("N", "North"),
        ("S", "South"),
        ("E", "East"),
        ("W", "West"),
    ):
        tricks = dds["tricks"][player]
        rows.append(
            f"| {label} | {tricks['NT']} | {tricks['S']} | "
            f"{tricks['H']} | {tricks['D']} | {tricks['C']} |"
        )
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
    parts = parse_contract(room.contract)
    if not parts:
        return f"実戦契約 {room.contract} は解析形式に変換できず。"
    level, strain, declarer = parts
    makeable = contract_makeable(dds, level, strain, declarer)
    dd_tricks = dds["tricks"][declarer][strain]
    gap = "不明" if room.tricks is None else f"{room.tricks - dd_tricks:+d}"
    return (
        f"実戦契約 {room.contract} はダブルダミー上"
        f"{'メイク可能' if makeable else 'メイク可能ではない'}。"
        f"{declarer}の最大トリック数は{dd_tricks}、実戦との差は{gap}トリック。"
    )


def _record_lines(name: str, room: RoomResult) -> list[str]:
    lines = [
        f"- **{name}**: 契約 {room.contract or '確認できず'} / "
        f"宣言者 {room.declarer or '確認できず'} / "
        f"リード {room.lead or '確認できず'} / "
        f"トリック {room.tricks if room.tricks is not None else '確認できず'} / "
        f"スコア {room.score if room.score is not None else '確認できず'}"
    ]
    if room.auction:
        lines.append(f"  - オークション: `{' – '.join(room.auction)}`")
    else:
        lines.append(
            f"  - オークション: {room.record_status or '公式記録では確認できず'}"
        )
    if room.play:
        lines.append("  - プレイ記録:")
        lines.extend(f"    - {item}" for item in room.play)
    else:
        lines.append(
            f"  - プレイ記録: {room.record_status or '公式記録では確認できず'}"
        )
    if room.play_url:
        lines.append(f"  - 公式記録URL: {room.play_url}")
    return lines


def _card_display(card: str | None) -> str:
    if not card:
        return "—"
    return f"{SUIT_SYMBOLS.get(card[0], card[0])}{card[1:]}"


def _lead_contract_result(analysis: dict, item: dict) -> str:
    tricks = item.get("declarer_tricks")
    if tricks is None:
        return "リード不可"
    delta = int(item["delta"])
    result = "=" if delta == 0 else f"{delta:+d}"
    strain = STRAIN_SYMBOLS[analysis["strain"]]
    return f"{tricks}（{analysis['level']}{strain}{result}）"


def _lead_analysis_markdown(room_name: str, analysis: dict) -> str:
    leader_name = PLAYER_NAMES.get(analysis["leader"], analysis["leader"])
    lines = [
        f"##### {room_name} — {analysis['contract']}（オープニングリーダー: {leader_name}）",
        "",
        "| スート | リーダーの保持 | 想定リード | 規則 | 宣言側DD最大トリック／契約結果 | 実戦リード |",
        "|---|---|---|---|---:|:---:|",
    ]
    for item in analysis["candidates"]:
        suit = SUIT_SYMBOLS[item["suit"]]
        holding = item["holding"] or "—"
        actual = "✓" if item["is_actual_lead"] else ""
        lines.append(
            f"| {suit} | {holding} | {_card_display(item['card'])} | "
            f"{LEAD_RULE_LABELS[item['rule']]} | "
            f"{_lead_contract_result(analysis, item)} | {actual} |"
        )

    actual = analysis.get("actual_lead_result")
    if actual:
        match_text = (
            "上記の規則候補に一致"
            if actual["matches_modelled_candidate"]
            else "上記の規則候補外"
        )
        delta = actual["delta"]
        result = "=" if delta == 0 else f"{delta:+d}"
        strain = STRAIN_SYMBOLS[analysis["strain"]]
        lines.extend(
            [
                "",
                f"- 実戦リード **{_card_display(actual['card'])}** は{match_text}。"
                f"固定リードDDSでは宣言側{actual['declarer_tricks']}トリック"
                f"（{analysis['level']}{strain}{result}）。",
            ]
        )
    elif analysis.get("actual_lead"):
        lines.extend(
            [
                "",
                f"- 実戦リード {_card_display(analysis['actual_lead'])} は"
                "リーダーの保持と照合できず、固定DDSを実行していない。",
            ]
        )
    return "\n".join(lines)


def board_markdown(board: BoardResult) -> tuple[str, dict[str, Any]]:
    deal = parse_pbn(board.pbn)
    dds = analyze(deal, board.dealer, board.vulnerability)
    swing = "IMP確認できず" if board.imp is None else f"日本に{board.imp:+d} IMP"
    room_lines = [f"- **スイング**: {swing}"]
    rooms = (("Open Room", board.open_room), ("Closed Room", board.closed_room))
    for name, room in rooms:
        if room:
            room_lines.extend(_record_lines(name, room))

    lead_analyses: dict[str, dict] = {}
    for name, room in rooms:
        if room and room.contract:
            result = opening_lead_analysis(deal, room.contract, room.lead)
            if result is not None:
                lead_analyses[name] = result

    payload = {
        "board": board.board,
        "dealer": board.dealer,
        "vulnerability": board.vulnerability,
        "pbn": board.pbn,
        "open_room": _room_dict(board.open_room),
        "closed_room": _room_dict(board.closed_room),
        "imp": board.imp,
        "notes": board.notes,
        "dds": dds,
        "opening_lead_dds": lead_analyses,
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

    if lead_analyses:
        text.extend(
            [
                "",
                "#### 想定オープニングリード別ダブルダミー解析",
                "",
                "規則は、スート契約では連続オナーからTop of Honorを優先し、"
                "それ以外は偶数枚から3rd、奇数枚からlowest。NT契約では"
                "連続オナーからTop of Honorを優先し、オナーを含むスートから"
                "4th best、オナーなしのスートはTop of Nothingと2nd bestを"
                "別候補として計算する。短いオナー・スートでは4th bestが"
                "存在しないため、3枚はlowest、ダブルトンはトップ、"
                "シングルトンはその1枚とする。",
                "",
            ]
        )
        for name in ("Open Room", "Closed Room"):
            analysis = lead_analyses.get(name)
            if analysis:
                text.extend([_lead_analysis_markdown(name, analysis), ""])

    text.extend(
        [
            "ダブルダミー値は全4ハンドを知る完全情報解析であり、実戦で同じ結果を"
            "出せることを意味しない。固定リードDDSも、初手以後は両陣営が"
            "完全情報で最善を尽くす仮定である。プレイ記録が不足する場合、"
            "特定の判断をミスと断定しない。",
        ]
    )
    return "\n".join(text), payload


def _rank_change_text(report: TeamReport) -> str:
    if report.rank_change is None:
        return "変動確認できず"
    if report.rank_change > 0:
        return f"{report.rank_change}位上昇"
    if report.rank_change < 0:
        return f"{abs(report.rank_change)}位下降"
    return "変動なし"


def team_markdown(report: TeamReport) -> tuple[str, dict[str, Any]]:
    match = report.match
    lines = [f"## {report.team} — Round {report.round_number}", ""]
    if match:
        vp = (
            "確認できず"
            if match.vp_for is None
            else f"{match.vp_for:.2f}–{match.vp_against:.2f}"
        )
        imp = (
            "確認できず"
            if match.imp_for is None
            else f"{match.imp_for}–{match.imp_against} IMP"
        )
        rank_label = report.rank_as_of or "取得時点"
        lines += [
            f"- 対戦相手: **{match.opponent}**",
            f"- IMP: **{imp}**",
            f"- VP: **{vp}**",
            f"- 順位（{rank_label}）: "
            f"{report.rank if report.rank is not None else '確認できず'}",
            f"- 前ラウンド順位: "
            f"{report.previous_rank if report.previous_rank is not None else '確認できず'}"
            f" / {_rank_change_text(report)}",
            f"- 次ラウンド: {report.next_opponent or '確認できず'} / "
            f"{report.next_start or '開始時刻確認できず'}",
            f"- Vugraph: {report.vugraph_status}"
            + (f" — {report.vugraph_url}" if report.vugraph_url else ""),
        ]
        if report.vugraph_archive_url:
            lines.append(f"- Vugraphアーカイブ: {report.vugraph_archive_url}")
        lines.append("")

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


def render_report(
    reports: list[TeamReport],
    round_number: int,
) -> tuple[str, dict[str, Any]]:
    blocks = [
        f"# WYOC Japan Tracker — Round {round_number}",
        "",
        "公式サイトで確認できた情報のみを掲載する。公式の過去順位が取得できない"
        "場合は、ラウンドごとのVPから再計算した順位であることを明記する。",
        "",
    ]
    payload: dict[str, Any] = {"round_number": round_number, "teams": []}
    for report in reports:
        block, team_payload = team_markdown(report)
        blocks += [block, ""]
        payload["teams"].append(team_payload)
    return "\n".join(blocks).rstrip() + "\n", payload


def write_outputs(
    markdown: str,
    data: dict[str, Any],
    output_dir: str,
    round_number: int,
) -> None:
    from pathlib import Path

    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / f"round-{round_number:02d}.md").write_text(
        markdown,
        encoding="utf-8",
    )
    (path / f"round-{round_number:02d}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
