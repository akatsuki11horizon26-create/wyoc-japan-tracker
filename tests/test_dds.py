from wyoc_tracker.dds import (
    analyze,
    contract_makeable,
    lead_ranks_for_holding,
    opening_lead_analysis,
)
from wyoc_tracker.pbn import parse_pbn


SAMPLE_PBN = (
    "N:96432.92.JT87.97 "
    "AT85.K3.6543.A86 "
    "Q7.J6.KQ92.QJT32 "
    "KJ.AQT8754.A.K54"
)


def test_dds_has_all_twenty_cells_and_par():
    deal = parse_pbn(SAMPLE_PBN)
    result = analyze(deal, "E", "E-W")
    assert set(result["tricks"]) == {"N", "S", "E", "W"}
    assert all(
        set(row) == {"NT", "S", "H", "D", "C"}
        for row in result["tricks"].values()
    )
    assert all(
        0 <= tricks <= 13
        for row in result["tricks"].values()
        for tricks in row.values()
    )
    assert isinstance(result["par_score"], int)
    assert contract_makeable(result, 6, "NT", "E")


def test_suit_leads_use_top_of_honor_then_third_or_lowest():
    assert lead_ranks_for_holding("KQ74", notrump=False) == [
        ("K", "top_of_honor")
    ]
    assert lead_ranks_for_holding("A864", notrump=False) == [
        ("6", "third_from_even")
    ]
    assert lead_ranks_for_holding("A85", notrump=False) == [
        ("5", "lowest_from_odd")
    ]


def test_notrump_leads_use_sequence_fourth_best_or_small_card_methods():
    assert lead_ranks_for_holding("QJ74", notrump=True) == [
        ("Q", "top_of_honor")
    ]
    assert lead_ranks_for_holding("K8642", notrump=True) == [
        ("4", "fourth_best")
    ]
    assert lead_ranks_for_holding("9863", notrump=True) == [
        ("9", "top_of_nothing"),
        ("8", "second_best"),
    ]


def test_short_notrump_honor_holdings_have_explicit_fallbacks():
    assert lead_ranks_for_holding("A83", notrump=True) == [
        ("3", "lowest_from_three")
    ]
    assert lead_ranks_for_holding("A8", notrump=True) == [
        ("A", "top_of_doubleton")
    ]
    assert lead_ranks_for_holding("A", notrump=True) == [
        ("A", "singleton")
    ]
    assert lead_ranks_for_holding("", notrump=True) == [(None, "void")]


def test_fixed_opening_lead_dds_returns_each_suit_and_marks_actual_lead():
    deal = parse_pbn(SAMPLE_PBN)
    result = opening_lead_analysis(deal, "6NT E", "DK")

    assert result is not None
    assert result["leader"] == "S"
    assert result["strain"] == "NT"
    assert {candidate["suit"] for candidate in result["candidates"]} == {
        "S",
        "H",
        "D",
        "C",
    }
    assert all(
        candidate["declarer_tricks"] is None
        or 0 <= candidate["declarer_tricks"] <= 13
        for candidate in result["candidates"]
    )
    diamond = next(
        candidate
        for candidate in result["candidates"]
        if candidate["card"] == "DK"
    )
    assert diamond["rule"] == "top_of_honor"
    assert diamond["is_actual_lead"]
    assert result["actual_lead_result"]["matches_modelled_candidate"]
