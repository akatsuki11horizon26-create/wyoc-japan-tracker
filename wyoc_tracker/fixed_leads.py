"""Repair missing fixed-opening-lead DDS entries before output validation."""

from __future__ import annotations

from typing import Any

from .dds import opening_lead_analysis, parse_contract
from .pbn import parse_pbn

ROOMS = (("Open Room", "open_room"), ("Closed Room", "closed_room"))


def hydrate_missing_fixed_leads(payload: dict[str, Any]) -> None:
    """Recompute a missing room analysis from the board PBN and room record.

    This does not weaken HTML validation. Real contracts are recomputed and the
    existing validator still rejects the report if DDS remains unavailable.
    Passed-out or absent contracts remain outside fixed-lead analysis.
    """

    for team in payload.get("teams", []):
        for board in team.get("selected_boards", []):
            analyses = board.setdefault("opening_lead_dds", {})
            deal = None
            for room_name, room_key in ROOMS:
                room = board.get(room_key)
                if not room or analyses.get(room_name):
                    continue
                contract = room.get("contract")
                if parse_contract(contract) is None:
                    continue
                if deal is None:
                    deal = parse_pbn(board["pbn"])
                analysis = opening_lead_analysis(deal, contract, room.get("lead"))
                if analysis is not None:
                    analyses[room_name] = analysis
