from wyoc_tracker import scraper
from wyoc_tracker.bbo import SCHEDULE_URL, configure_scraper, matches_round


def test_bbo_schedule_uses_non_javascript_offset_endpoint():
    assert SCHEDULE_URL.endswith("v2schedule.php?offset=0")


def test_swiss_round_labels_are_recognized():
    assert matches_round("BBO2-2026WYTC-Hefei U26-SW1", 1)
    assert matches_round("2026 WYTC SW03", 3)
    assert not matches_round("2026 WYTC U26-SW2", 1)


def test_scraper_configuration_sets_schedule_endpoint_and_matcher():
    original_url = scraper.VUGRAPH_URL
    original_matcher = scraper._matches_round
    try:
        configure_scraper(scraper)
        assert scraper.VUGRAPH_URL == SCHEDULE_URL
        assert scraper._matches_round("U21-SW2", 2)
    finally:
        scraper.VUGRAPH_URL = original_url
        scraper._matches_round = original_matcher
