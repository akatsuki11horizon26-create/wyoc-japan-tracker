"""Deterministic selection of notable boards."""

from __future__ import annotations

from .models import BoardResult


def _contract_score(board: BoardResult) -> tuple[int, int, int]:
    rooms = [r for r in (board.open_room, board.closed_room) if r]
    contracts = [(r.contract or "").upper() for r in rooms]
    contract_interest = sum(
        1
        for contract in contracts
        if contract and (contract[:1] in {"5", "6", "7"} or "XX" in contract or "X" in contract)
    )
    result_difference = 0
    if len(rooms) == 2 and rooms[0].tricks is not None and rooms[1].tricks is not None:
        result_difference = abs(rooms[0].tricks - rooms[1].tricks)
    return (abs(board.imp or 0), contract_interest, result_difference)


def select_boards(boards: list[BoardResult], limit: int = 5) -> list[BoardResult]:
    """Select up to ``limit`` boards, prioritising signed IMP swings first."""

    if limit < 1:
        return []
    return sorted(boards, key=lambda board: (_contract_score(board), -board.board), reverse=True)[:limit]
