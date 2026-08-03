"""Double-dummy analysis backed by Bo Haglund's DDS through endplay."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .pbn import Deal, RANKS, SUITS

try:
    from endplay.dds import analyse_play, calc_dd_table, par
    from endplay.types import Deal as EndplayDeal
    from endplay.types import Denom, Player, Vul
except ImportError as exc:  # pragma: no cover - exercised in minimal installs
    raise RuntimeError("endplay is required for DDS analysis; install requirements.txt") from exc

DENOMS = (
    ("NT", Denom.nt),
    ("S", Denom.spades),
    ("H", Denom.hearts),
    ("D", Denom.diamonds),
    ("C", Denom.clubs),
)
DENOM_ENUM = dict(DENOMS)
PLAYER_ENUM = {"N": Player.north, "E": Player.east, "S": Player.south, "W": Player.west}
NEXT_PLAYER = {"N": "E", "E": "S", "S": "W", "W": "N"}
VUL_ENUM = {"None": Vul.none, "N-S": Vul.ns, "E-W": Vul.ew, "All": Vul.both, "Both": Vul.both}
HONOURS = "AKQJT"
CONTRACT_RE = re.compile(
    r"^\s*([1-7])\s*(NT|[SHDC])\s*(?:XX|X)?\s*([NESW])\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ContractResult:
    level: int
    strain: str
    declarer: str
    tricks: int

    @property
    def text(self) -> str:
        return f"{self.level}{self.strain}{self.declarer}="


def _endplay_deal(
    deal: Deal,
    *,
    first: str | None = None,
    trump: str | None = None,
) -> EndplayDeal:
    kwargs = {}
    if first is not None:
        kwargs["first"] = PLAYER_ENUM[first]
    if trump is not None:
        kwargs["trump"] = DENOM_ENUM[trump]
    return EndplayDeal(deal.pbn, **kwargs)


def _contract_to_dict(contract) -> dict:
    return {
        "level": int(contract.level),
        "strain": contract.denom.abbr,
        "declarer": contract.declarer.abbr,
        "tricks": int(contract.level + 6),
    }


def analyze(deal: Deal, dealer: str = "N", vulnerability: str = "None") -> dict:
    """Compute all 20 DDS cells and WBF-style par metadata."""

    dealer = dealer.upper()
    if dealer not in PLAYER_ENUM:
        raise ValueError(f"Invalid dealer: {dealer}")
    if vulnerability not in VUL_ENUM:
        raise ValueError(f"Invalid vulnerability: {vulnerability}")
    table = calc_dd_table(_endplay_deal(deal))
    tricks = {
        player: {
            denom_key: int(table[denom, PLAYER_ENUM[player]])
            for denom_key, denom in DENOMS
        }
        for player in ("N", "S", "E", "W")
    }
    par_list = par(table, VUL_ENUM[vulnerability], PLAYER_ENUM[dealer])
    contracts = [_contract_to_dict(contract) for contract in par_list]
    return {
        "tricks": tricks,
        "par_score": int(par_list.score),
        "par_contracts": contracts,
    }


def contract_makeable(dds: dict, level: int, strain: str, declarer: str) -> bool:
    strain = strain.upper()
    if strain == "NT":
        key = "NT"
    elif strain in {"S", "H", "D", "C"}:
        key = strain
    else:
        raise ValueError(f"Invalid strain: {strain}")
    return int(dds["tricks"][declarer.upper()][key]) >= level + 6


def parse_contract(contract: str | None) -> tuple[int, str, str] | None:
    """Return ``(level, strain, declarer)`` for a normalized result contract."""

    if not contract:
        return None
    match = CONTRACT_RE.match(contract)
    if not match:
        return None
    return int(match.group(1)), match.group(2).upper(), match.group(3).upper()


def _ordered_holding(cards: str) -> str:
    present = set(cards.upper())
    return "".join(rank for rank in RANKS if rank in present)


def _top_touching_honour(cards: str) -> str | None:
    """Return the top card of the highest touching honour sequence."""

    present = set(cards)
    for upper, lower in zip(HONOURS, HONOURS[1:]):
        if upper in present and lower in present:
            return upper
    return None


def lead_ranks_for_holding(cards: str, *, notrump: bool) -> list[tuple[str | None, str]]:
    """Select convention-based lead ranks for one suit holding.

    Top of Honor overrides the length lead whenever the holding contains at
    least two touching honours. Against a suit contract, third from an even
    length and lowest from an odd length are used. Against notrump, fourth
    best is used from an honour holding. With no honour, both Top of Nothing
    and second best are retained as separate agreement candidates.
    """

    holding = _ordered_holding(cards)
    if not holding:
        return [(None, "void")]

    sequence_top = _top_touching_honour(holding)
    if sequence_top is not None:
        return [(sequence_top, "top_of_honor")]

    length = len(holding)
    if not notrump:
        if length == 1:
            return [(holding[0], "singleton")]
        if length == 2:
            return [(holding[0], "top_of_doubleton")]
        if length % 2 == 0:
            return [(holding[2], "third_from_even")]
        return [(holding[-1], "lowest_from_odd")]

    contains_honour = any(rank in HONOURS for rank in holding)
    if contains_honour:
        if length >= 4:
            return [(holding[3], "fourth_best")]
        if length == 3:
            return [(holding[-1], "lowest_from_three")]
        if length == 2:
            return [(holding[0], "top_of_doubleton")]
        return [(holding[0], "singleton")]

    candidates = [(holding[0], "top_of_nothing")]
    if length >= 2:
        candidates.append((holding[1], "second_best"))
    return candidates


def _normalise_card(card: str | None) -> str | None:
    if not card:
        return None
    value = (
        str(card)
        .upper()
        .replace("♠", "S")
        .replace("♥", "H")
        .replace("♦", "D")
        .replace("♣", "C")
        .replace("10", "T")
    )
    value = re.sub(r"[^SHDCAKQJT2-9]", "", value)
    match = re.search(r"([SHDC])([AKQJT2-9])", value)
    return "".join(match.groups()) if match else None


def _declarer_tricks_after_lead(
    deal: Deal,
    *,
    leader: str,
    strain: str,
    card: str,
) -> int:
    endplay_deal = _endplay_deal(deal, first=leader, trump=strain)
    solved = analyse_play(endplay_deal, [card], declarer_is_first=False)
    if len(solved) < 2:
        raise RuntimeError(f"DDS did not return a post-lead value for {card}")
    tricks = int(solved[1])
    if not 0 <= tricks <= 13:
        raise RuntimeError(f"DDS returned invalid trick count {tricks} for {card}")
    return tricks


def opening_lead_analysis(
    deal: Deal,
    contract: str | None,
    actual_lead: str | None = None,
) -> dict | None:
    """Analyse convention-based opening leads for one room contract.

    Each candidate card is fixed as trick one's opening lead before DDS is run.
    The returned trick count is therefore declarer's maximum after that exact
    lead, under double-dummy play by both sides.
    """

    parts = parse_contract(contract)
    if parts is None:
        return None
    level, strain, declarer = parts
    leader = NEXT_PLAYER[declarer]
    target = level + 6
    actual = _normalise_card(actual_lead)
    cache: dict[str, int] = {}
    candidates: list[dict] = []

    def tricks_for(card: str) -> int:
        if card not in cache:
            cache[card] = _declarer_tricks_after_lead(
                deal,
                leader=leader,
                strain=strain,
                card=card,
            )
        return cache[card]

    for suit in SUITS:
        holding = deal.hand(leader)[suit]
        for rank, rule in lead_ranks_for_holding(holding, notrump=strain == "NT"):
            card = None if rank is None else f"{suit}{rank}"
            declarer_tricks = None if card is None else tricks_for(card)
            candidates.append(
                {
                    "suit": suit,
                    "holding": _ordered_holding(holding),
                    "card": card,
                    "rule": rule,
                    "declarer_tricks": declarer_tricks,
                    "target_tricks": target,
                    "delta": None if declarer_tricks is None else declarer_tricks - target,
                    "makeable": None if declarer_tricks is None else declarer_tricks >= target,
                    "is_actual_lead": card is not None and card == actual,
                }
            )

    candidate_cards = {item["card"] for item in candidates if item["card"]}
    actual_result = None
    if actual is not None:
        actual_holding = deal.hand(leader).get(actual[0], "")
        if actual[1:] in actual_holding:
            actual_tricks = tricks_for(actual)
            actual_result = {
                "card": actual,
                "declarer_tricks": actual_tricks,
                "target_tricks": target,
                "delta": actual_tricks - target,
                "makeable": actual_tricks >= target,
                "matches_modelled_candidate": actual in candidate_cards,
            }

    return {
        "contract": contract,
        "level": level,
        "strain": strain,
        "declarer": declarer,
        "leader": leader,
        "actual_lead": actual,
        "actual_lead_result": actual_result,
        "candidates": candidates,
    }
