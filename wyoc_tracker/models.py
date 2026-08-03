"""Serializable domain models used by the scraper and report renderer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RoomResult:
    contract: str | None = None
    declarer: str | None = None
    lead: str | None = None
    tricks: int | None = None
    score: int | None = None
    auction_url: str | None = None
    play_url: str | None = None


@dataclass
class BoardResult:
    board: int
    dealer: str
    vulnerability: str
    pbn: str
    open_room: RoomResult | None = None
    closed_room: RoomResult | None = None
    imp: int | None = None
    notes: list[str] = field(default_factory=list)


@dataclass
class MatchResult:
    team: str
    opponent: str
    match_id: str
    round_number: int
    team_position: int | None = None
    vp_for: float | None = None
    vp_against: float | None = None
    imp_for: int | None = None
    imp_against: int | None = None
    board_url: str | None = None
    boards: list[BoardResult] = field(default_factory=list)


@dataclass
class TeamReport:
    team: str
    round_number: int
    match: MatchResult | None = None
    rank: int | None = None
    rank_as_of: str | None = None
    previous_rank: int | None = None
    next_opponent: str | None = None
    next_start: str | None = None
    vugraph_status: str = "確認できず"
    vugraph_url: str | None = None
    selected_boards: list[BoardResult] = field(default_factory=list)
