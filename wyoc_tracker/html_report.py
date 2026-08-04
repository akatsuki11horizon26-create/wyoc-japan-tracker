"""HTML output and strict fixed-opening-lead DDS validation."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from .dds import parse_contract
from .pbn import SUITS, SUIT_SYMBOLS, parse_pbn

DDS_NOTE = (
    "ダブルダミー値は全4ハンドを知る完全情報解析であり、実戦で同じ結果を"
    "出せることを意味しない。固定リードDDSも、初手以後は両陣営が"
    "完全情報で最善を尽くす仮定である。プレイ記録が不足する場合、"
    "特定の判断をミスと断定しない。"
)
PLAYERS = ("N", "E", "S", "W")
PLAYER_NAMES = {"N": "North", "E": "East", "S": "South", "W": "West"}
VUL_PLAYERS = {
    "None": set(),
    "N-S": {"N", "S"},
    "E-W": {"E", "W"},
    "All": set(PLAYERS),
    "Both": set(PLAYERS),
}
RULE_LABELS = {
    "top_of_honor": "Top of Honor",
    "third_from_even": "3rd from even",
    "lowest_from_odd": "lowest from odd",
    "fourth_best": "4th best",
    "top_of_nothing": "Top of Nothing",
    "second_best": "2nd best",
    "lowest_from_three": "lowest from three",
    "top_of_doubleton": "top of doubleton",
    "singleton": "singleton",
    "void": "void",
}
PASS_OUT_RE = re.compile(r"^\s*(?:PASS(?:ED)?\s*OUT|ALL\s*PASS|AP|P)\s*$", re.I)


def normalize_markdown(markdown: str) -> str:
    """Keep the DDS caution exactly once, near the report beginning."""
    body = markdown.replace(DDS_NOTE, "").replace("\n\n\n", "\n\n")
    lines = body.splitlines()
    insert_at = 2 if len(lines) >= 2 else len(lines)
    lines[insert_at:insert_at] = ["", f"> **DDS注意**: {DDS_NOTE}", ""]
    return "\n".join(lines).rstrip() + "\n"


def _is_passed_out(contract: Any) -> bool:
    return bool(contract and PASS_OUT_RE.match(str(contract)))


def validate_fixed_leads(payload: dict[str, Any]) -> None:
    """Refuse HTML when any real contract lacks complete fixed-lead DDS values."""
    failures: list[str] = []
    for team in payload.get("teams", []):
        team_name = team.get("team", "unknown")
        for board in team.get("selected_boards", []):
            board_no = board.get("board", "?")
            analyses = board.get("opening_lead_dds") or {}
            for room_name, room_key in (("Open Room", "open_room"), ("Closed Room", "closed_room")):
                room = board.get(room_key)
                if not room or not room.get("contract"):
                    continue
                contract = room.get("contract")
                label = f"{team_name} Board {board_no} {room_name}"
                if _is_passed_out(contract):
                    continue
                if parse_contract(str(contract)) is None:
                    failures.append(f"{label}: unparseable contract {contract!r}")
                    continue
                analysis = analyses.get(room_name)
                if not analysis:
                    failures.append(f"{label}: analysis missing")
                    continue
                candidates = analysis.get("candidates") or []
                if not candidates:
                    failures.append(f"{label}: candidates missing")
                for item in candidates:
                    if item.get("rule") != "void" and item.get("declarer_tricks") is None:
                        failures.append(f"{label}: {item.get('card') or item.get('suit')} DDS missing")
                if room.get("lead") and not analysis.get("actual_lead_result"):
                    failures.append(f"{label}: actual lead DDS missing")
    if failures:
        raise RuntimeError("HTML generation blocked by incomplete fixed-lead DDS: " + "; ".join(failures))


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def _hand_html(board: dict[str, Any]) -> str:
    deal = parse_pbn(board["pbn"])
    dealer = board.get("dealer")
    vulnerable = VUL_PLAYERS.get(board.get("vulnerability", "None"), set())
    cards = []
    for player in PLAYERS:
        hand = deal.hand(player)
        rows = "".join(
            f"<div><span class='suit'>{SUIT_SYMBOLS[suit]}</span> {_esc(hand[suit] or '—')}</div>"
            for suit in SUITS
        )
        cls = "seat vulnerable" if player in vulnerable else "seat nonvulnerable"
        d = " D" if player == dealer else ""
        cards.append(
            f"<section class='{cls}' data-seat='{player}'><h4>{PLAYER_NAMES[player]}{d}</h4>{rows}</section>"
        )
    return "<div class='deal'>" + "".join(cards) + "</div>"


def _room_html(room_name: str, room: dict[str, Any] | None, analysis: dict[str, Any] | None) -> str:
    if not room:
        return f"<section class='room'><h4>{_esc(room_name)}</h4><p>公式記録なし</p></section>"
    details = (
        f"<p>契約 <strong>{_esc(room.get('contract') or '確認できず')}</strong> / "
        f"リード {_esc(room.get('lead') or '確認できず')} / "
        f"トリック {_esc(room.get('tricks') if room.get('tricks') is not None else '確認できず')} / "
        f"スコア {_esc(room.get('score') if room.get('score') is not None else '確認できず')}</p>"
    )
    if _is_passed_out(room.get("contract")):
        return f"<section class='room'><h4>{_esc(room_name)}</h4>{details}<p>Passed Outのため固定リードDDS対象外。</p></section>"
    if not analysis:
        return f"<section class='room'><h4>{_esc(room_name)}</h4>{details}</section>"
    rows = []
    for item in analysis.get("candidates", []):
        result = "—" if item.get("declarer_tricks") is None else str(item["declarer_tricks"])
        actual = "✓" if item.get("is_actual_lead") else ""
        rows.append(
            "<tr>"
            f"<td>{_esc(SUIT_SYMBOLS.get(item.get('suit'), item.get('suit')))}</td>"
            f"<td>{_esc(item.get('holding') or '—')}</td>"
            f"<td>{_esc(item.get('card') or '—')}</td>"
            f"<td>{_esc(RULE_LABELS.get(item.get('rule'), item.get('rule')))}</td>"
            f"<td>{_esc(result)}</td><td>{actual}</td></tr>"
        )
    table = (
        "<table><thead><tr><th>スート</th><th>保持</th><th>固定リード</th>"
        "<th>規則</th><th>宣言側DDトリック</th><th>実戦</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )
    actual = analysis.get("actual_lead_result")
    actual_text = ""
    if actual:
        actual_text = (
            f"<p>実戦リード {_esc(actual.get('card'))}: 宣言側DD "
            f"{_esc(actual.get('declarer_tricks'))}トリック</p>"
        )
    return f"<section class='room'><h4>{_esc(room_name)}</h4>{details}{table}{actual_text}</section>"


def render_html(payload: dict[str, Any]) -> str:
    validate_fixed_leads(payload)
    blocks = []
    for team in payload.get("teams", []):
        boards = []
        for board in team.get("selected_boards", []):
            analyses = board.get("opening_lead_dds") or {}
            dds = board.get("dds") or {}
            dd_rows = "".join(
                f"<tr><th>{PLAYER_NAMES[p]}</th>" + "".join(
                    f"<td>{_esc((dds.get('tricks') or {}).get(p, {}).get(s, '—'))}</td>"
                    for s in ("NT", "S", "H", "D", "C")
                ) + "</tr>"
                for p in ("N", "S", "E", "W")
            )
            dd_table = (
                "<table><thead><tr><th>宣言者</th><th>NT</th><th>♠</th><th>♥</th><th>♦</th><th>♣</th></tr></thead>"
                f"<tbody>{dd_rows}</tbody></table>"
            )
            boards.append(
                f"<article class='board'><h3>Board {_esc(board.get('board'))}</h3>"
                f"<p>Dealer: {_esc(board.get('dealer'))} / Vulnerability: {_esc(board.get('vulnerability'))} / "
                f"日本側IMP: {_esc(board.get('imp'))}</p>"
                f"{_hand_html(board)}<h4>DDS table</h4>{dd_table}"
                f"{_room_html('Open Room', board.get('open_room'), analyses.get('Open Room'))}"
                f"{_room_html('Closed Room', board.get('closed_room'), analyses.get('Closed Room'))}</article>"
            )
        blocks.append(f"<section class='team'><h2>{_esc(team.get('team'))} — Round {_esc(team.get('round_number'))}</h2>{''.join(boards)}</section>")
    return f"""<!doctype html>
<html lang='ja'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>WYOC Japan Tracker Round {_esc(payload.get('round_number'))}</title>
<style>
body{{font-family:system-ui,sans-serif;max-width:1400px;margin:auto;padding:20px;line-height:1.5;background:#f5f5f5}}
h1,h2,h3,h4{{margin:.4em 0}} .notice,.board,.team{{background:white;padding:16px;margin:16px 0;border-radius:10px}}
.deal{{display:grid;grid-template-areas:'. n .' 'w . e' '. s .';grid-template-columns:1fr 1fr 1fr;gap:12px;max-width:850px;margin:16px auto}}
.seat[data-seat='N']{{grid-area:n}}.seat[data-seat='E']{{grid-area:e}}.seat[data-seat='S']{{grid-area:s}}.seat[data-seat='W']{{grid-area:w}}
.seat{{padding:10px;border:3px solid white;background:#222;color:white;border-radius:8px;min-width:180px}}.seat.vulnerable{{border-color:#e00000}}.seat.nonvulnerable{{border-color:white;box-shadow:0 0 0 1px #888}}
.suit{{display:inline-block;width:1.4em}} table{{border-collapse:collapse;width:100%;margin:10px 0}}th,td{{border:1px solid #aaa;padding:6px;text-align:center}}th{{background:#eee}}.room{{margin-top:18px;overflow-x:auto}}
</style></head><body><h1>WYOC Japan Tracker — Round {_esc(payload.get('round_number'))}</h1>
<div class='notice'><strong>DDS注意:</strong> {_esc(DDS_NOTE)}</div>{''.join(blocks)}</body></html>"""


def write_outputs(markdown: str, payload: dict[str, Any], output_dir: str, round_number: int) -> None:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    normalized = normalize_markdown(markdown)
    (output / f"round-{round_number:02d}.md").write_text(normalized, encoding="utf-8")
    (output / f"round-{round_number:02d}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rendered = render_html(payload)
    (output / f"round-{round_number:02d}.html").write_text(rendered, encoding="utf-8")
