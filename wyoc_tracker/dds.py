"""Double-dummy analysis backed by Bo Haglund's DDS through endplay."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .pbn import Deal

try:
    from endplay.dds import calc_dd_table, par
    from endplay.types import Deal as EndplayDeal
    from endplay.types import Denom, Player, Vul
except ImportError as exc:  # pragma: no cover - exercised in minimal installs
    raise RuntimeError("endplay is required for DDS analysis; install requirements.txt") from exc

DENOMS = (("NT", Denom.nt), ("S", Denom.spades), ("H", Denom.hearts), ("D", Denom.diamonds), ("C", Denom.clubs))
PLAYER_ENUM = {"N": Player.north, "E": Player.east, "S": Player.south, "W": Player.west}
VUL_ENUM = {"None": Vul.none, "N-S": Vul.ns, "E-W": Vul.ew, "All": Vul.both, "Both": Vul.both}


@dataclass(frozen=True)
class ContractResult:
    level: int
    strain: str
    declarer: str
    tricks: int

    @property
    def text(self) -> str:
        return f"{self.level}{self.strain}{self.declarer}="


def _endplay_deal(deal: Deal) -> EndplayDeal:
    return EndplayDeal(deal.pbn)


def _contract_to_dict(contract) -> dict:
    return {"level": int(contract.level), "strain": contract.denom.abbr, "declarer": contract.declarer.abbr, "tricks": int(contract.level + 6)}


def analyze(deal: Deal, dealer: str = "N", vulnerability: str = "None") -> dict:
    """Compute all 20 DDS cells and WBF-style par metadata."""

    dealer = dealer.upper()
    if dealer not in PLAYER_ENUM:
        raise ValueError(f"Invalid dealer: {dealer}")
    if vulnerability not in VUL_ENUM:
        raise ValueError(f"Invalid vulnerability: {vulnerability}")
    table = calc_dd_table(_endplay_deal(deal))
    tricks = {p: {d: int(table[denom, PLAYER_ENUM[p]]) for d, denom in DENOMS} for p in ("N", "S", "E", "W")}
    par_list = par(table, VUL_ENUM[vulnerability], PLAYER_ENUM[dealer])
    contracts = [_contract_to_dict(c) for c in par_list]
    return {"tricks": tricks, "par_score": int(par_list.score), "par_contracts": contracts}


def contract_makeable(dds: dict, level: int, strain: str, declarer: str) -> bool:
    strain = strain.upper()
    if strain == "NT":
        key = "NT"
    elif strain in {"S", "H", "D", "C"}:
        key = strain
    else:
        raise ValueError(f"Invalid strain: {strain}")
    return int(dds["tricks"][declarer.upper()][key]) >= level + 6
