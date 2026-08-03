from pathlib import Path

from wyoc_tracker.scraper import parse_board_details, parse_hands_page, parse_round_start


def test_current_wbf_fixture_parsing():
    root = Path(__file__).parent
    html = (root / "fixtures" / "hands.html").read_text(encoding="utf-8")
    hands = parse_hands_page(html)
    assert 6 in hands
    assert hands[6][0:2] == ("E", "E-W")
    assert hands[6][2].startswith("N:96432.92.JT87.97")


def test_board_details_parsing_uses_tracked_team_perspective():
    root = Path(__file__).parent
    hands = parse_hands_page((root / "fixtures" / "hands.html").read_text(encoding="utf-8"))
    html = (root / "fixtures" / "boarddetails.html").read_text(encoding="utf-8")

    home_board = next(board for board in parse_board_details(html, hands, team_position=0) if board.board == 6)
    visitor_board = next(board for board in parse_board_details(html, hands, team_position=1) if board.board == 6)

    assert home_board.imp == 12
    assert visitor_board.imp == -12
    assert home_board.open_room and home_board.open_room.contract == "6NT E"
    assert home_board.closed_room and home_board.closed_room.contract == "7H W"


def test_round_start_is_converted_from_china_to_japan_time():
    html = '<a href="RoundTeams.asp?qroundno=2">Round 2 11:50</a>'
    assert parse_round_start(html, 2) == "12:50 JST"
