from wyoc_tracker.pbn import PBNError, cross_layout, parse_pbn


SAMPLE = "N:96432.92.JT87.97 AT85.K3.6543.A86 Q7.J6.KQ92.QJT32 KJ.AQT8754.A.K54"


def test_parse_complete_deal_and_cross_layout():
    deal = parse_pbn(SAMPLE)
    assert deal.pbn == SAMPLE
    text = cross_layout(deal, 6, "E", "E-W")
    assert "North" in text and "West" in text and "East" in text
    assert "♠ 96432" in text
    assert "♥ AQT8754" in text


def test_rejects_incomplete_or_duplicate_deal():
    try:
        parse_pbn("N:AKQ.2.3.4 2.3.4.5 6.7.8.9 T.J.Q.K")
    except PBNError:
        pass
    else:
        raise AssertionError("incomplete PBN must fail")
