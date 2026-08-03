from pathlib import Path

from wyoc_tracker.scraper import parse_board_details, parse_hands_page, parse_round_page


def test_current_wbf_fixture_parsing():
    root = Path(__file__).parent
    # Keep the test network-independent: use the captured fixture checked into data.
    html = (root / "fixtures" / "hands.html").read_text(encoding="utf-8")
    hands = parse_hands_page(html)
    assert 6 in hands
    assert hands[6][0:2] == ("E", "E-W")
    assert hands[6][2].startswith("N:96432.92.JT87.97")


def test_board_details_parsing():
    root = Path(__file__).parent
    hands = parse_hands_page((root / "fixtures" / "hands.html").read_text(encoding="utf-8"))
    boards = parse_board_details((root / "fixtures" / "boarddetails.html").read_text(encoding="utf-8"), hands)
    board = next(x for x in boards if x.board == 6)
    assert board.imp == 12
    assert board.open_room and board.open_room.contract == "6NT E"
    assert board.closed_room and board.closed_room.contract == "7H W"
