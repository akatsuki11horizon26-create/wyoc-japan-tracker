"""Strict PBN parsing and hand-record formatting."""

from __future__ import annotations

import re
from dataclasses import dataclass

SUITS = ("S", "H", "D", "C")
RANKS = "AKQJT98765432"
PLAYERS = ("N", "E", "S", "W")
PLAYER_NAMES = {"N": "North", "E": "East", "S": "South", "W": "West"}
SUIT_SYMBOLS = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
SUIT_NAMES = {"S": "Spades", "H": "Hearts", "D": "Diamonds", "C": "Clubs"}
CARD_RE = re.compile(r"^[AKQJT2-9]*$")


class PBNError(ValueError):
    """Raised for an invalid or incomplete PBN deal."""


@dataclass(frozen=True)
class Deal:
    """A complete bridge deal in PBN order (N, E, S, W)."""

    hands: dict[str, dict[str, str]]
    first: str = "N"

    @property
    def pbn(self) -> str:
        order = [PLAYERS[(PLAYERS.index(self.first) + offset) % 4] for offset in range(4)]
        return self.first + ":" + " ".join(".".join(self.hands[p][s] or "" for s in SUITS) for p in order)

    def hand(self, player: str) -> dict[str, str]:
        return self.hands[player.upper()]


def parse_pbn(pbn: str) -> Deal:
    """Parse and validate a complete four-hand PBN deal.

    PBN may contain a prefix such as ``N:``. Every card must occur exactly once;
    incomplete deals are rejected because DDS results would not be meaningful.
    """

    if not isinstance(pbn, str) or ":" not in pbn:
        raise PBNError("PBN must include a first-player prefix such as N:")
    prefix, body = pbn.split(":", 1)
    first = prefix.strip().upper()
    if first not in PLAYERS:
        raise PBNError(f"Invalid first player: {first!r}")
    hands_raw = body.split()
    if len(hands_raw) != 4:
        raise PBNError(f"Expected four hands, got {len(hands_raw)}")
    hands: dict[str, dict[str, str]] = {}
    all_cards: list[str] = []
    for offset, hand_text in enumerate(hands_raw):
        parts = hand_text.split(".")
        if len(parts) != 4:
            raise PBNError(f"Hand {offset + 1} must contain four suits")
        player = PLAYERS[(PLAYERS.index(first) + offset) % 4]
        hand: dict[str, str] = {}
        for suit, cards in zip(SUITS, parts):
            cards = cards.upper()
            if cards and not CARD_RE.fullmatch(cards):
                raise PBNError(f"Invalid cards in {player} {suit}: {cards!r}")
            if len(cards) != len(set(cards)):
                raise PBNError(f"Duplicate rank in {player} {suit}: {cards!r}")
            hand[suit] = cards
            all_cards.extend(f"{suit}{rank}" for rank in cards)
        if sum(len(v) for v in hand.values()) != 13:
            raise PBNError(f"{player} has {sum(len(v) for v in hand.values())} cards, not 13")
        hands[player] = hand
    expected = {f"{s}{r}" for s in SUITS for r in RANKS}
    actual = set(all_cards)
    if len(all_cards) != 52 or actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise PBNError(f"Deal is not a complete 52-card deck; missing={missing}, extra={extra}")
    return Deal(hands=hands, first=first)


def _display_hand(hand: dict[str, str]) -> list[str]:
    return [f"{SUIT_SYMBOLS[s]} {hand[s] or '—'}" for s in SUITS]


def cross_layout(deal: Deal, board: int | str, dealer: str, vulnerability: str) -> str:
    """Render a hand record in the required North/West-East/South layout."""

    n, e, s, w = (deal.hand(p) for p in PLAYERS)
    nlines, elines, slines, wlines = map(_display_hand, (n, e, s, w))
    width = max(13, max(len(x) for x in wlines), max(len(x) for x in elines))
    dealer_name = PLAYER_NAMES.get(dealer.upper(), dealer.title())
    out = [f"Board {board}", f"Dealer: {dealer_name}", f"Vulnerability: {vulnerability}", "", "                  North"]
    out.extend(f"                  {line}" for line in nlines)
    out.append("")
    out.append(f"{'West':<{width + 8}}East")
    for left, right in zip(wlines, elines):
        out.append(f"{left:<{width + 8}}{right}")
    out.append("")
    out.append("                  South")
    out.extend(f"                  {line}" for line in slines)
    return "\n".join(out)


def hands_as_pbn(deal: Deal) -> str:
    return deal.pbn
