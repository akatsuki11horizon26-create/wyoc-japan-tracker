"""WBF microsite scraper for the current Hefei event layout."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .models import BoardResult, MatchResult, RoomResult, TeamReport
from .pbn import SUITS
from .select import select_boards

BASE_URL = "https://db.worldbridge.org/Repository/tourn/hefei.26/microsite/"
VUGRAPH_URL = "https://www.bridgebase.com/vugraph/v2schedule.php"
TOURNAMENTS = {"U26 JAPAN": 2660, "U21 JAPAN": 2661, "U26 Women JAPAN": 2662}
USER_AGENT = "WYOC-Japan-Tracker/0.2 (+https://github.com/akatsuki11horizon26-create/wyoc-japan-tracker)"


class FetchError(RuntimeError):
    pass


def fetch(url: str, session: requests.Session | None = None, cache_dir: str | None = None) -> str:
    s = session or requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    try:
        response = s.get(url, timeout=30)
    except requests.RequestException as exc:
        raise FetchError(f"GET {url}: {exc}") from exc
    if response.status_code != 200:
        raise FetchError(f"GET {url}: HTTP {response.status_code}")
    if cache_dir:
        path = Path(cache_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / (hashlib.sha256(url.encode()).hexdigest() + ".html")).write_text(response.text, encoding="utf-8")
    return response.text


def _text(node) -> str:
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def _num(text: str, as_float: bool = False):
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text.replace(",", ""))
    if not match:
        return None
    return float(match.group()) if as_float else int(float(match.group()))


def _absolute(href: str, base_url: str) -> str:
    if href.startswith(("http://", "https://", "/")) or "/" in href.split("?", 1)[0]:
        return urljoin(base_url, href)
    if base_url.rstrip("/").endswith("microsite"):
        return urljoin(base_url, "Asp/" + href)
    return urljoin(base_url, href)


def _team_key(team_name: str) -> str:
    return team_name.upper().replace(" WOMEN", "").replace("U26 ", "").replace("U21 ", "")


def parse_round_page(html: str, round_number: int, team_name: str, base_url: str = BASE_URL) -> MatchResult:
    soup = BeautifulSoup(html, "html.parser")
    target = _team_key(team_name)
    for card in soup.select(".match[data-mid]"):
        teams = card.select(".m-team")
        if len(teams) != 2:
            continue
        names = [_text(team.select_one(".name")) for team in teams]
        matching = [index for index, name in enumerate(names) if target in name.upper()]
        if not matching:
            continue
        index = matching[0]
        imp = [_num(_text(value)) for value in card.select(".m-team .imp")]
        vp = [_num(_text(value), as_float=True) for value in card.select(".m-team .vp")]
        table_link = card.select_one("a.tbl-link[href]")
        return MatchResult(
            team=names[index],
            opponent=names[1 - index],
            match_id=card.get("data-mid", ""),
            round_number=round_number,
            team_position=index,
            imp_for=imp[index] if len(imp) == 2 else None,
            imp_against=imp[1 - index] if len(imp) == 2 else None,
            vp_for=vp[index] if len(vp) == 2 else None,
            vp_against=vp[1 - index] if len(vp) == 2 else None,
            board_url=_absolute(table_link["href"], base_url) if table_link else None,
        )
    raise FetchError(f"Team {team_name} not found on round {round_number} page")


def parse_ranking(html: str, team_name: str) -> int | None:
    soup = BeautifulSoup(html, "html.parser")
    target = _team_key(team_name)
    for row in soup.select(".rank-list .rank-row"):
        if target in _text(row.select_one(".team")).upper():
            return _num(_text(row.select_one(".pos")))
    return None


def _normalize_suit(text: str) -> str:
    return text.replace("♠", "S").replace("♥", "H").replace("♦", "D").replace("♣", "C")


def parse_hands_page(html: str) -> dict[int, tuple[str, str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[int, tuple[str, str, str]] = {}
    for card in soup.select(".deal-card"):
        board = _num(_text(card.select_one(".dc-brd")))
        info = _text(card.select_one(".dc-info"))
        dealer_match = re.search(r"Dealer\s+(North|East|South|West)", info, re.I)
        vul_match = re.search(r"(None|N-S|E-W|All)\s+vulnerable", info, re.I)
        if board is None or not dealer_match or not vul_match:
            continue
        dealer = dealer_match.group(1)[0].upper()
        vulnerability = {"NONE": "None", "N-S": "N-S", "E-W": "E-W", "ALL": "All"}[vul_match.group(1).upper()]
        hands: dict[str, dict[str, str]] = {}
        for css_class, player in (("pos-n", "N"), ("pos-e", "E"), ("pos-s", "S"), ("pos-w", "W")):
            hand = card.select_one(f".{css_class} .hand")
            if not hand:
                break
            suits: dict[str, str] = {}
            for row, suit in zip(hand.select(".row"), SUITS):
                raw = re.sub(r"^[♠♥♦♣]\s*", "", _text(row))
                suits[suit] = "" if raw in {"", "—", "–", "-"} else raw
            hands[player] = suits
        if len(hands) == 4:
            pbn = "N:" + " ".join(".".join(hands[player][suit] for suit in SUITS) for player in ("N", "E", "S", "W"))
            result[board] = dealer, vulnerability, pbn
    return result


def _parse_room(node, base_url: str) -> RoomResult:
    contract = _normalize_suit(_text(node.select_one(".cell.contract"))) or None
    if contract:
        contract = re.sub(r"\s+", " ", contract).strip()
        contract = re.sub(
            r"^([1-7])\s*(NT|[SHDC])\s*(XX|X)?\s+([NESW])$",
            lambda match: f"{match.group(1)}{match.group(2)}{match.group(3) or ''} {match.group(4)}",
            contract,
        ) or None
    declarer_match = re.search(r"(?:^|\s)([NESW])$", contract or "")
    lead = re.sub(r"\s+", "", _normalize_suit(_text(node.select_one(".cell.lead .cv")))) or None
    play = node.select_one(".cell.tricks a[href]")
    return RoomResult(
        contract=contract,
        declarer=declarer_match.group(1) if declarer_match else None,
        lead=lead,
        tricks=_num(_text(node.select_one(".cell.tricks .cv"))),
        score=_num(_text(node.select_one(".cell.score .score"))),
        play_url=_absolute(play["href"], base_url) if play else None,
    )


def _signed_board_imp(card, team_position: int | None) -> int | None:
    """Return IMPs from the tracked team's perspective.

    WBF marks the first team/home gain as ``imp-h`` and the second/visitor gain
    as ``imp-v``. Exactly one is normally populated.
    """
    home = _num(_text(card.select_one(".imp-cell .imp-h")))
    visitor = _num(_text(card.select_one(".imp-cell .imp-v")))
    if home is None and visitor is None:
        return None
    if team_position == 0:
        return home if home is not None else -visitor
    if team_position == 1:
        return visitor if visitor is not None else -home
    return None


def parse_board_details(
    html: str,
    hands: dict[int, tuple[str, str, str]],
    base_url: str = BASE_URL,
    team_position: int | None = None,
) -> list[BoardResult]:
    soup = BeautifulSoup(html, "html.parser")
    boards: list[BoardResult] = []
    for card in soup.select(".board-card"):
        board = _num(_text(card.select_one(".brd-cell a.brd")))
        if board is None or board not in hands:
            continue
        dealer, vulnerability, pbn = hands[board]
        open_node = card.select_one(".room.open")
        closed_node = card.select_one(".room.closed")
        boards.append(
            BoardResult(
                board=board,
                dealer=dealer,
                vulnerability=vulnerability,
                pbn=pbn,
                open_room=_parse_room(open_node, base_url) if open_node else None,
                closed_room=_parse_room(closed_node, base_url) if closed_node else None,
                imp=_signed_board_imp(card, team_position),
            )
        )
    return boards


def parse_vugraph(html: str, team: str, opponent: str | None = None) -> tuple[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    target = _team_key(team)
    if target not in _text(soup).upper():
        return "日本戦の中継予定なし", None
    for link in soup.find_all("a", href=True):
        label = _text(link).upper()
        if target in label and (not opponent or opponent.upper() in label):
            return "Vugraph中継あり", urljoin(VUGRAPH_URL, link["href"])
    return "放送カード未発表", VUGRAPH_URL


def parse_round_start(html: str, round_number: int) -> str | None:
    """Parse the published China time and return Japan time (UTC+9)."""
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.select(f'a[href*="qroundno={round_number}"]'):
        match = re.search(r"\b(\d{1,2}:\d{2})\b", _text(link))
        if match:
            china = datetime.strptime(match.group(1), "%H:%M")
            return (china + timedelta(hours=1)).strftime("%H:%M JST")
    return None


def make_report(
    team: str,
    round_number: int,
    tournament_id: int,
    session: requests.Session | None = None,
    cache_dir: str | None = None,
) -> TeamReport:
    base = BASE_URL
    round_url = urljoin(base, f"Asp/RoundTeams.asp?qtournid={tournament_id}&qroundno={round_number}")
    match = parse_round_page(fetch(round_url, session, cache_dir), round_number, team, base)
    hands_url = urljoin(base, f"Asp/handsacross.asp?qtournid={tournament_id}&qround={round_number}")
    hands = parse_hands_page(fetch(hands_url, session, cache_dir))
    if match.board_url:
        match.boards = parse_board_details(
            fetch(match.board_url, session, cache_dir), hands, base, match.team_position
        )

    rank_url = urljoin(base, f"RunningScores/Asp/RoundTeamsConditStatClassicMod.asp?qtournid={tournament_id}&qshowflag=1")
    rank = parse_ranking(fetch(rank_url, session, cache_dir), team)
    report = TeamReport(
        team=team,
        round_number=round_number,
        match=match,
        rank=rank,
        rank_as_of="公式順位ページの取得時点",
        selected_boards=select_boards(match.boards),
    )

    try:
        next_url = urljoin(base, f"Asp/RoundTeams.asp?qtournid={tournament_id}&qroundno={round_number + 1}")
        next_match = parse_round_page(fetch(next_url, session, cache_dir), round_number + 1, team, base)
        report.next_opponent = next_match.opponent
        report.next_start = parse_round_start(fetch(urljoin(base, "Results.htm"), session, cache_dir), round_number + 1)
    except FetchError:
        pass

    try:
        vugraph = fetch(VUGRAPH_URL, session, cache_dir)
        report.vugraph_status, report.vugraph_url = parse_vugraph(vugraph, team, match.opponent)
    except FetchError:
        report.vugraph_status = "Vugraph公式スケジュールを取得できず"
    return report


def fetch_reports(round_number: int, session: requests.Session | None = None, cache_dir: str | None = None) -> list[TeamReport]:
    shared_session = session or requests.Session()
    return [make_report(team, round_number, tournament_id, shared_session, cache_dir) for team, tournament_id in TOURNAMENTS.items()]
