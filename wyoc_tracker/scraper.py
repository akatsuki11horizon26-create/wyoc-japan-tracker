"""WBF and BBO scrapers for the 2026 Hefei youth event.

The public pages are not a stable API. Parsers therefore keep missing values as
``None`` and never synthesize bridge results that were not present in a source.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from .models import BoardResult, MatchResult, RoomResult, TeamReport
from .pbn import SUITS
from .select import select_boards

BASE_URL = "https://db.worldbridge.org/Repository/tourn/hefei.26/microsite/"
RESULTS_URL = urljoin(BASE_URL, "Results.htm")
VUGRAPH_URL = "https://www.bridgebase.com/vugraph/v2schedule.php"
VUGRAPH_ARCHIVE_URL = "https://www.bridgebase.com/vugraph_archives/vugraph_archives.php"
TOURNAMENTS = {"U26 JAPAN": 2660, "U21 JAPAN": 2661, "U26 Women JAPAN": 2662}
USER_AGENT = "WYOC-Japan-Tracker/1.0 (+https://github.com/akatsuki11horizon26-create/wyoc-japan-tracker)"


class FetchError(RuntimeError):
    pass


def _cache_path(cache_dir: str | None, url: str) -> Path | None:
    if not cache_dir:
        return None
    return Path(cache_dir) / (hashlib.sha256(url.encode()).hexdigest() + ".html")


def fetch(
    url: str,
    session: requests.Session | None = None,
    cache_dir: str | None = None,
    *,
    refresh: bool = False,
) -> str:
    """Fetch a page with an optional persistent cache."""

    cached = _cache_path(cache_dir, url)
    if cached and cached.exists() and not refresh:
        return cached.read_text(encoding="utf-8")

    client = session or requests.Session()
    client.headers.update({"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    try:
        response = client.get(url, timeout=30)
    except requests.RequestException as exc:
        raise FetchError(f"GET {url}: {exc}") from exc
    if response.status_code != 200:
        raise FetchError(f"GET {url}: HTTP {response.status_code}")

    response.encoding = response.apparent_encoding or response.encoding or "utf-8"
    text = response.text
    if cached:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(text, encoding="utf-8")
    return text


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
    return team_name.upper().replace(" WOMEN", "").replace("U26 ", "").replace("U21 ", "").strip()


def _team_aliases(team_name: str) -> set[str]:
    upper = team_name.upper()
    aliases = {_team_key(team_name), upper}
    if "WOMEN" in upper:
        aliases.update({"U26W JAPAN", "JAPAN U26W", "JAPAN WOMEN"})
    elif "U21" in upper:
        aliases.update({"U21 JAPAN", "JAPAN U21"})
    elif "U26" in upper:
        aliases.update({"U26 JAPAN", "JAPAN U26"})
    return {alias for alias in aliases if alias}


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


def parse_round_standings(html: str) -> dict[str, float]:
    """Return VP earned in one round for every team found on the page."""

    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, float] = {}
    for card in soup.select(".match[data-mid]"):
        teams = card.select(".m-team")
        if len(teams) != 2:
            continue
        for team in teams:
            name = _text(team.select_one(".name"))
            vp = _num(_text(team.select_one(".vp")), as_float=True)
            if name and vp is not None:
                result[name] = float(vp)
    return result


def parse_ranking(html: str, team_name: str) -> int | None:
    soup = BeautifulSoup(html, "html.parser")
    target = _team_key(team_name)
    for row in soup.select(".rank-list .rank-row"):
        if target in _text(row.select_one(".team")).upper():
            return _num(_text(row.select_one(".pos")))
    return None


def parse_round_candidates(html: str) -> list[int]:
    values: set[int] = set()
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all("a", href=True):
        href = str(link.get("href", ""))
        for pattern in (r"[?&]qroundno=(\d+)", r"[?&]qround=(\d+)"):
            match = re.search(pattern, href, re.I)
            if match:
                values.add(int(match.group(1)))
    return sorted(values)


def _match_is_completed(match: MatchResult) -> bool:
    return all(
        value is not None
        for value in (match.imp_for, match.imp_against, match.vp_for, match.vp_against)
    )


def discover_latest_completed_round(
    session: requests.Session | None = None,
    cache_dir: str | None = None,
) -> int:
    """Find the latest round with completed scores in all three Japan events."""

    client = session or requests.Session()
    results_html = fetch(RESULTS_URL, client, cache_dir, refresh=True)
    candidates = parse_round_candidates(results_html)
    if not candidates:
        raise FetchError("No round links found on the official results page")

    for round_number in reversed(candidates):
        complete = True
        for team, tournament_id in TOURNAMENTS.items():
            url = urljoin(BASE_URL, f"Asp/RoundTeams.asp?qtournid={tournament_id}&qroundno={round_number}")
            try:
                match = parse_round_page(fetch(url, client, cache_dir, refresh=True), round_number, team)
            except FetchError:
                complete = False
                break
            if not _match_is_completed(match):
                complete = False
                break
        if complete:
            return round_number
    raise FetchError("No completed Japan round found")


def compute_rank_as_of_round(
    team_name: str,
    tournament_id: int,
    round_number: int,
    session: requests.Session | None = None,
    cache_dir: str | None = None,
) -> int | None:
    """Reconstruct a historical rank from cumulative VP.

    Equal VP totals receive equal rank because an unavailable official tie-break
    is never guessed.
    """

    if round_number < 1:
        return None
    client = session or requests.Session()
    totals: dict[str, float] = {}
    for number in range(1, round_number + 1):
        url = urljoin(BASE_URL, f"Asp/RoundTeams.asp?qtournid={tournament_id}&qroundno={number}")
        round_values = parse_round_standings(fetch(url, client, cache_dir, refresh=False))
        if not round_values:
            return None
        for name, vp in round_values.items():
            totals[name] = totals.get(name, 0.0) + vp

    target_name = next((name for name in totals if _team_key(team_name) in name.upper()), None)
    if target_name is None:
        return None
    target = totals[target_name]
    return 1 + sum(1 for value in totals.values() if value > target + 1e-9)


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


_BID_RE = re.compile(r"(?<![A-Z0-9])(?:PASS|P|XX|X|[1-7](?:NT|[SHDC♠♥♦♣]))(?![A-Z0-9])", re.I)
_CARD_RE = re.compile(r"(?:[SHDC♠♥♦♣](?:10|[2-9TJQKA]))", re.I)


def _extract_auction(node: Tag | None) -> list[str]:
    if node is None:
        return []
    candidates: list[str] = []
    for attr in ("title", "data-title", "data-content", "data-original-title", "data-auction"):
        value = node.get(attr)
        if value:
            candidates.append(str(value))
    for child in node.select(".auction, .bidding, .bid-table, .popover-content, [data-auction]"):
        candidates.append(_text(child))
        if child.get("data-auction"):
            candidates.append(str(child.get("data-auction")))

    bids: list[str] = []
    for candidate in candidates:
        normalized = _normalize_suit(BeautifulSoup(candidate, "html.parser").get_text(" ", strip=True)).upper()
        for match in _BID_RE.finditer(normalized):
            bid = match.group().upper()
            if bid == "P":
                bid = "PASS"
            bids.append(bid)
    return bids


def _parse_room(node: Tag, base_url: str) -> RoomResult:
    contract_node = node.select_one(".cell.contract")
    contract = _normalize_suit(_text(contract_node)) or None
    if contract:
        contract = re.sub(r"\s+", " ", contract).strip()
        contract_match = re.search(r"([1-7])\s*(NT|[SHDC])\s*(XX|X)?\s*([NESW])", contract, re.I)
        contract = (
            f"{contract_match.group(1)}{contract_match.group(2).upper()}{(contract_match.group(3) or '').upper()} {contract_match.group(4).upper()}"
            if contract_match
            else contract
        )
    declarer_match = re.search(r"(?:^|\s)([NESW])$", contract or "")
    lead = re.sub(r"\s+", "", _normalize_suit(_text(node.select_one(".cell.lead .cv")))) or None
    play_link = node.select_one(".cell.tricks a[href]")
    play_url = _absolute(play_link["href"], base_url) if play_link else None
    auction = _extract_auction(contract_node)
    return RoomResult(
        contract=contract,
        declarer=declarer_match.group(1) if declarer_match else None,
        lead=lead,
        tricks=_num(_text(node.select_one(".cell.tricks .cv"))),
        score=_num(_text(node.select_one(".cell.score .score"))),
        auction_url=play_url if auction else None,
        play_url=play_url,
        auction=auction,
    )


def _signed_board_imp(card: Tag, team_position: int | None) -> int | None:
    home = _num(_text(card.select_one(".imp-cell .imp-h")))
    visitor = _num(_text(card.select_one(".imp-cell .imp-v")))
    if home is None and visitor is None:
        values = [_num(_text(node)) for node in card.select(".imp-cell span")]
        values = [value for value in values if value is not None]
        if len(values) >= 2:
            home, visitor = values[0], values[1]
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


def _play_lines(section: Tag) -> list[str]:
    lines: list[str] = []
    for row in section.select("tr"):
        cells = [_text(cell) for cell in row.select("th, td")]
        if not cells:
            continue
        joined = " | ".join(cell for cell in cells if cell)
        normalized = _normalize_suit(joined)
        cards = _CARD_RE.findall(normalized)
        if cards or re.search(r"\bTRICK\s*\d+\b", normalized, re.I):
            lines.append(joined)
    return lines[:20]


def _room_sections(soup: BeautifulSoup) -> dict[str, Tag]:
    result: dict[str, Tag] = {}
    selectors = {
        "open": (".room.open", ".open-room", "#open", "[data-room='open']"),
        "closed": (".room.closed", ".closed-room", "#closed", "[data-room='closed']"),
    }
    for room, options in selectors.items():
        for selector in options:
            node = soup.select_one(selector)
            if node:
                result[room] = node
                break

    if len(result) < 2:
        for heading in soup.find_all(["h1", "h2", "h3", "h4", "caption", "strong"]):
            label = _text(heading).lower()
            room = "open" if "open room" in label else "closed" if "closed room" in label else None
            if room and room not in result:
                candidate = heading.find_next(["table", "div"])
                if isinstance(candidate, Tag):
                    result[room] = candidate
    return result


def parse_play_details(html: str) -> dict[str, dict[str, list[str]]]:
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, dict[str, list[str]]] = {}
    for room, section in _room_sections(soup).items():
        result[room] = {"auction": _extract_auction(section), "play": _play_lines(section)}
    return result


def enrich_selected_boards(
    boards: list[BoardResult],
    session: requests.Session | None = None,
    cache_dir: str | None = None,
) -> None:
    client = session or requests.Session()
    for board in boards:
        urls = [room.play_url for room in (board.open_room, board.closed_room) if room and room.play_url]
        if not urls:
            for room in (board.open_room, board.closed_room):
                if room:
                    room.record_status = "公式記録ではオークション／プレイを確認できず"
            continue
        try:
            details = parse_play_details(fetch(urls[0], client, cache_dir, refresh=False))
        except FetchError as exc:
            board.notes.append(str(exc))
            continue
        for key, room in (("open", board.open_room), ("closed", board.closed_room)):
            if room is None:
                continue
            values = details.get(key, {})
            if not room.auction:
                room.auction = list(values.get("auction", []))
            room.play = list(values.get("play", []))
            if room.auction and not room.auction_url:
                room.auction_url = room.play_url
            if not room.auction and not room.play:
                room.record_status = "公式記録ではオークション／プレイを確認できず"


def _row_candidates(soup: BeautifulSoup) -> list[Tag]:
    rows = list(soup.select("tr"))
    if rows:
        return rows
    return [node for node in soup.select("li, .match, .event, .row") if isinstance(node, Tag)]


def _matches_team(text: str, team: str, opponent: str | None) -> bool:
    upper = text.upper()
    team_match = any(alias in upper for alias in _team_aliases(team))
    opponent_match = not opponent or _team_key(opponent) in upper or opponent.upper() in upper
    return team_match and opponent_match


def _matches_round(text: str, round_number: int | None) -> bool:
    if round_number is None:
        return True
    upper = text.upper().replace("_", " ")
    patterns = (
        rf"\bROUND\s*0*{round_number}\b",
        rf"\bRR\s*0*{round_number}\b",
        rf"\bR\s*0*{round_number}\b",
        rf"\b0*{round_number}\s*/",
    )
    return any(re.search(pattern, upper) for pattern in patterns)


def parse_vugraph_schedule(
    html: str,
    team: str,
    opponent: str | None = None,
    round_number: int | None = None,
) -> tuple[str, str | None]:
    soup = BeautifulSoup(html, "html.parser")
    page_text = _text(soup).upper()
    event_present = "WYTC" in page_text or "HEFEI" in page_text
    for row in _row_candidates(soup):
        text = _text(row)
        if not _matches_team(text, team, opponent) or not _matches_round(text, round_number):
            continue
        link = row.find("a", href=True)
        return "Vugraph中継あり", urljoin(VUGRAPH_URL, link["href"]) if link else VUGRAPH_URL
    if event_present:
        return "日本戦の中継予定なし", None
    return "放送カード未発表", VUGRAPH_URL


def parse_vugraph_archive(
    html: str,
    team: str,
    opponent: str | None = None,
    round_number: int | None = None,
) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for row in _row_candidates(soup):
        text = _text(row)
        upper = text.upper()
        if "WYTC" not in upper and "HEFEI" not in upper:
            continue
        if not _matches_team(text, team, opponent) or not _matches_round(text, round_number):
            continue
        links = row.find_all("a", href=True)
        preferred = next((link for link in links if "VIEW" in _text(link).upper()), None)
        chosen = preferred or (links[0] if links else None)
        if chosen:
            return urljoin(VUGRAPH_ARCHIVE_URL, chosen["href"])
    return None


def parse_round_start(html: str, round_number: int) -> str | None:
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
    latest_completed_round: int | None = None,
) -> TeamReport:
    client = session or requests.Session()
    is_latest = latest_completed_round == round_number
    round_url = urljoin(BASE_URL, f"Asp/RoundTeams.asp?qtournid={tournament_id}&qroundno={round_number}")
    match = parse_round_page(fetch(round_url, client, cache_dir, refresh=is_latest), round_number, team)
    hands_url = urljoin(BASE_URL, f"Asp/handsacross.asp?qtournid={tournament_id}&qround={round_number}")
    hands = parse_hands_page(fetch(hands_url, client, cache_dir, refresh=is_latest))
    if match.board_url:
        match.boards = parse_board_details(
            fetch(match.board_url, client, cache_dir, refresh=is_latest),
            hands,
            BASE_URL,
            match.team_position,
        )

    if is_latest:
        rank_url = urljoin(BASE_URL, f"RunningScores/Asp/RoundTeamsConditStatClassicMod.asp?qtournid={tournament_id}&qshowflag=1")
        rank = parse_ranking(fetch(rank_url, client, cache_dir, refresh=True), team)
        rank_as_of = f"公式順位ページ・Round {round_number}取得時点"
    else:
        rank = compute_rank_as_of_round(team, tournament_id, round_number, client, cache_dir)
        rank_as_of = f"Round {round_number}までの累積VP再計算（同VPは同順位）"

    previous_rank = (
        compute_rank_as_of_round(team, tournament_id, round_number - 1, client, cache_dir)
        if round_number > 1
        else None
    )
    report = TeamReport(
        team=team,
        round_number=round_number,
        match=match,
        rank=rank,
        rank_as_of=rank_as_of,
        previous_rank=previous_rank,
        rank_change=(previous_rank - rank) if previous_rank is not None and rank is not None else None,
        selected_boards=select_boards(match.boards),
    )
    enrich_selected_boards(report.selected_boards, client, cache_dir)

    try:
        next_url = urljoin(BASE_URL, f"Asp/RoundTeams.asp?qtournid={tournament_id}&qroundno={round_number + 1}")
        next_match = parse_round_page(fetch(next_url, client, cache_dir, refresh=True), round_number + 1, team)
        report.next_opponent = next_match.opponent
        report.next_start = parse_round_start(fetch(RESULTS_URL, client, cache_dir, refresh=True), round_number + 1)
    except FetchError:
        pass

    try:
        schedule_html = fetch(VUGRAPH_URL, client, cache_dir, refresh=True)
        report.vugraph_status, report.vugraph_url = parse_vugraph_schedule(
            schedule_html, team, match.opponent, round_number
        )
    except FetchError:
        report.vugraph_status = "Vugraph公式スケジュールを取得できず"

    try:
        archive_html = fetch(VUGRAPH_ARCHIVE_URL, client, cache_dir, refresh=True)
        report.vugraph_archive_url = parse_vugraph_archive(
            archive_html, team, match.opponent, round_number
        )
        if report.vugraph_archive_url:
            report.vugraph_status = "Vugraphアーカイブあり"
    except FetchError:
        pass
    return report


def fetch_reports(
    round_number: int,
    session: requests.Session | None = None,
    cache_dir: str | None = None,
    latest_completed_round: int | None = None,
) -> list[TeamReport]:
    shared_session = session or requests.Session()
    return [
        make_report(
            team,
            round_number,
            tournament_id,
            shared_session,
            cache_dir,
            latest_completed_round,
        )
        for team, tournament_id in TOURNAMENTS.items()
    ]
