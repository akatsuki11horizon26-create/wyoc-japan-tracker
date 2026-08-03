from wyoc_tracker.dds import analyze, contract_makeable
from wyoc_tracker.pbn import parse_pbn


def test_dds_has_all_twenty_cells_and_par():
    deal = parse_pbn("N:96432.92.JT87.97 AT85.K3.6543.A86 Q7.J6.KQ92.QJT32 KJ.AQT8754.A.K54")
    result = analyze(deal, "E", "E-W")
    assert set(result["tricks"]) == {"N", "S", "E", "W"}
    assert all(set(row) == {"NT", "S", "H", "D", "C"} for row in result["tricks"].values())
    assert all(0 <= n <= 13 for row in result["tricks"].values() for n in row.values())
    assert isinstance(result["par_score"], int)
    assert contract_makeable(result, 6, "NT", "E")
