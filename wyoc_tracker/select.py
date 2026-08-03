"""Board ordering for complete round reports."""

from __future__ import annotations

from .models import BoardResult


def select_boards(boards: list[BoardResult], limit: int | None = None) -> list[BoardResult]:
    """Return every board in board-number order.

    ``limit`` is retained for API compatibility but intentionally ignored: round
    reports must contain the complete Open/Closed Room board set.
    """

    return sorted(boards, key=lambda board: board.board)
