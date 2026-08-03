"""WBF microsite scraper for the current Heifei event layout.

The WBF pages are static HTML and have changed presentation over time. Parsing is
therefore intentionally class-based, with all URLs in one configuration object;
unknown or missing fields remain ``None`` instead of being guessed.
"""

from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .models import BoardResult, MatchResult, RoomResult, TeamReport
from .pbn import SUITS
from .select import select_boards


BASE_URL = "https://db.worldbridge.org/Repository/tourn/hefei.26/microsite/"
VUGRAPH_URL = "https://www.bridgebase.com/vugraph/v2schedule.php"
TOURNAMENTS = {"U26 JAPAN": 2660, "U21 JAPAN": 2661, "U26 Women JAPAN": 2662}
USER_AGENT = "WYOC-Japan-Tracker/0.1 (+https://github.com/akatsuki11horizon26-create/wyoc-japan-tracker)"


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
    text = response.text
    if cache_dir:
        from pathlib import Path
        import hashlib
        path = Path(cache_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / (hashlib.sha256(url.encode()).hexdigest() + ".html")).write_text(text, encoding="utf-8")
    return text


def _text(node) -> str:
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


def _num(text: str, as_float: bool = False):
    m = re.search(r"[-+]?\d+(?:\.\d+)?", text.replace(",", ""))
    if not m:
        return None
    return float(m.group()) if as_float else int(float(m.group()))


def _absolute(href: str, base_url: str) -> str:
    if href.startswith(("http://", "https://", "/")) or "/" in href.split("?", 1)[0]:
        return urljoin(base_url, href)
    # WBF microsite pages link to sibling ASP files without the Asp/ prefix.
    if base_url.rstrip("/").endswith("microsite"):
        return urljoin(base_url, "Asp/" + href)
    return urljoin(base_url, href)


def parse_round_page(html: str, round_number: int, team_name: str, base_url: str = BASE_URL) -> MatchResult:
    soup = BeautifulSoup(html, "html.parser")
    target = team_name.upper().replace(" WOMEN", "").replace("U26 ", "").replace("U21 ", "")
    for card in soup.select(".match[data-mid]"):
        teams = card.select(".m-team")
        if len(teams) != 2:
            continue
        names = [_text(t.select_one(".name")) for t in teams]
        if not any(target in n.upper() for n in names):
            continue
        idx = next(i for i, n in enumerate(names) if target in n.upper())
        other = names[1 - idx]
        imp = [_num(_text(x)) for x in card.select(".m-team .imp")]
        vp = [_num(_text(x), as_float=True) for x in card.select(".m-team .vp")]
        table_link = card.select_one("a.tbl-link[href]")
        href = table_link["href"] if table_link else ""
        match_id = card.get("data-mid", "")
        # The first numerical value in the match card is the team total.
        return MatchResult(team=names[idx], opponent=other, match_id=match_id, round_number=round_number, imp_for=imp[idx] if len(imp) == 2 else None, imp_against=imp[1 - idx] if len(imp) == 2 else None, vp_for=vp[idx] if len(vp) == 2 else None, vp_against=vp[1 - idx] if len(vp) == 2 else None, board_url=_absolute(href, base_url))
    raise FetchError(f"Team {team_name} not found on round {round_number} page")


def parse_ranking(html: str, team_name: str) -> int | None:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select(".rank-list .rank-row")
    target = team_name.upper().replace(" WOMEN", "").replace("U26 ", "").replace("U21 ", "")
    for row in rows:
        name = _text(row.select_one(".team"))
        if target in name.upper():
            return _num(_text(row.select_one(".pos")))
    return None


def _normalize_suit(text: str) -> str:
    return text.replace("♠", "S").replace("♥", "H").replace("♦", "D").replace("♣", "C").replace("NT", "NT")


def parse_hands_page(html: str) -> dict[int, tuple[str, str, str]]:
    """Return board -> (dealer, vulnerability, North-first PBN)."""
    soup = BeautifulSoup(html, "html.parser")
    result = {}
    for card in soup.select(".deal-card"):
        link = card.select_one(".dc-brd")
        if not link:
            continue
        board = _num(_text(link))
        info = _text(card.select_one(".dc-info"))
        dealer_m = re.search(r"Dealer\s+(North|East|South|West)", info, re.I)
        vul_m = re.search(r"(None|N-S|E-W|All)\s+vulnerable", info, re.I)
        if board is None or not dealer_m or not vul_m:
            continue
        dealer = dealer_m.group(1)[0].upper()
        vul_raw = vul_m.group(1).upper()
        vulnerability = {"NONE": "None", "N-S": "N-S", "E-W": "E-W", "ALL": "All"}[vul_raw]
        hands: dict[str, dict[str, str]] = {}
        for position, player in (("pos-n", "N"), ("pos-e", "E"), ("pos-s", "S"), ("pos-w", "W")):
            hand = card.select_one(f".{position} .hand")
            if not hand:
                break
            suits = {}
            for row, suit in zip(hand.select(".row"), SUITS):
                raw = _text(row)
                raw = re.sub(r"^[♠♥♦♣]\s*", "", raw)
                suits[suit] = "" if raw in {"", "—", "–", "-"} else raw
            hands[player] = suits
        if len(hands) == 4:
            pbn = "N:" + " ".join(".".join(hands[p][s] for s in SUITS) for p in ("N", "E", "S", "W"))
            result[board] = (dealer, vulnerability, pbn)
    return result


def _parse_room(node, base_url: str) -> RoomResult:
    contract_node = node.select_one(".cell.contract")
    contract = _normalize_suit(_text(contract_node)) if contract_node else None
    contract = re.sub(r"\s+", " ", contract).strip() if contract else None
    contract = re.sub(r"^([1-7])\s*(NT|[SHDC])\s*(XX|X)?\s+([NESW])$", lambda m: f"{m.group(1)}{m.group(2)}{m.group(3) or ''} {m.group(4)}", contract or "") or None
    declarer = None
    m = re.search(r"(?:^|\s)([NESW])$", contract or "")
    if m:
        declarer = m.group(1)
    lead = _normalize_suit(_text(node.select_one(".cell.lead .cv"))) or None
    lead = re.sub(r"\s+", "", lead) or None
    tricks_node = node.select_one(".cell.tricks .cv")
    score_node = node.select_one(".cell.score .score")
    play = node.select_one(".cell.tricks a[href]")
    return RoomResult(contract=contract, declarer=declarer, lead=lead, tricks=_num(_text(tricks_node)), score=_num(_text(score_node)), play_url=_absolute(play["href"], base_url) if play else None)


def parse_board_details(html: str, hands: dict[int, tuple[str, str, str]], base_url: str = BASE_URL) -> list[BoardResult]:
    soup = BeautifulSoup(html, "html.parser")
    boards: list[BoardResult] = []
    for card in soup.select(".board-card"):
        link = card.select_one(".brd-cell a.brd")
        board = _num(_text(link))
        if board is None or board not in hands:
            continue
        dealer, vulnerability, pbn = hands[board]
        imp = _num(_text(card.select_one(".imp-cell .imp-h")))
        open_node, closed_node = card.select_one(".room.open"), card.select_one(".room.closed")
        boards.append(BoardResult(board=board, dealer=dealer, vulnerability=vulnerability, pbn=pbn, open_room=_parse_room(open_node, base_url) if open_node else None, closed_room=_parse_room(closed_node, base_url) if closed_node else None, imp=imp))
    return boards


def parse_vugraph(html: str, team: str, opponent: str | None = None) -> tuple[str, str | None]:
    text = _text(BeautifulSoup(html, "html.parser"))
    if team.upper().replace("U26 ", "") not in text.upper():
        return "日本戦の中継予定なし", None
    # The schedule site may expose several links; return the first schedule URL
    # unless a direct table link is present. Never invent an archive URL.
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        label = _text(a)
        if team.upper().replace("U26 ", "") in label.upper() and (not opponent or opponent.upper() in label.upper()):
            return "Vugraph中継あり", a["href"]
    return "放送カード未発表", VUGRAPH_URL


def parse_round_start(html: str, round_number: int) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.select(f'a[href*="qroundno={round_number}"]'):
        label = _text(a)
        m = re.search(r"\b(\d{1,2}:\d{2})\b", label)
        if m:
            return m.group(1)
    return None


def make_report(team: str, round_number: int, tournament_id: int, session: requests.Session | None = None, cache_dir: str | None = None) -> TeamReport:
    base = BASE_URL
    round_url = urljoin(base, f"Asp/RoundTeams.asp?qtournid={tournament_id}&qroundno={round_number}")
    round_html = fetch(round_url, session, cache_dir)
    match = parse_round_page(round_html, round_number, team, base)
    hands_url = urljoin(base, f"Asp/handsacross.asp?qtournid={tournament_id}&qround={round_number}")
    hands = parse_hands_page(fetch(hands_url, session, cache_dir))
    board_url = match.board_url
    if board_url:
        match.boards = parse_board_details(fetch(board_url, session, cache_dir), hands, base)
    # Ranking pages include a static current ranking panel; if absent it stays unknown.
    rank_url = urljoin(base, f"RunningScores/Asp/RoundTeamsConditStatClassicMod.asp?qtournid={tournament_id}&qshowflag=1")
    rank = parse_ranking(fetch(rank_url, session, cache_dir), team)
    report = TeamReport(team=team, round_number=round_number, match=match, rank=rank, selected_boards=select_boards(match.boards))
    if round_number > 1:
        try:
            previous_rank_html = fetch(urljoin(base, f"RunningScores/Asp/RoundTeamsConditStatClassicMod.asp?qtournid={tournament_id}&qroundno={round_number - 1}&qshowflag=1"), session, cache_dir)
            report.previous_rank = parse_ranking(previous_rank_html, team)
        except FetchError:
            pass
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
    s = session or requests.Session()
    return [make_report(team, round_number, tid, s, cache_dir) for team, tid in TOURNAMENTS.items()]
