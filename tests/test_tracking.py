import json

from wyoc_tracker.history import apply_history, write_snapshot
from wyoc_tracker.models import BoardResult, RoomResult, TeamReport
from wyoc_tracker.scraper import (
    parse_play_details,
    parse_round_candidates,
    parse_vugraph_archive,
    parse_vugraph_schedule,
)
from wyoc_tracker.select import select_boards


def test_round_candidates_are_unique_and_sorted():
    html = """
    <a href='RoundTeams.asp?qtournid=1&qroundno=3'>R3</a>
    <a href='RoundTeams.asp?qtournid=2&qroundno=1'>R1</a>
    <a href='handsacross.asp?qtournid=1&qround=3'>Hands</a>
    """
    assert parse_round_candidates(html) == [1, 3]


def test_play_details_extracts_room_records():
    html = """
    <div class='room open'>
      <div class='auction' data-auction='1C Pass 1H X 2H Pass Pass Pass'></div>
      <table><tr><th>Trick</th><th>West</th><th>North</th><th>East</th><th>South</th></tr>
      <tr><td>1</td><td>S2</td><td>SA</td><td>S3</td><td>S4</td></tr></table>
    </div>
    <div class='room closed'>
      <div data-auction='1NT Pass 3NT Pass Pass Pass'></div>
      <table><tr><td>1</td><td>HK</td><td>H2</td><td>H3</td><td>HA</td></tr></table>
    </div>
    """
    result = parse_play_details(html)
    assert result['open']['auction'][:3] == ['1C', 'PASS', '1H']
    assert result['open']['play']
    assert result['closed']['auction'][0] == '1NT'


def test_vugraph_schedule_and_archive_match_round():
    schedule = """
    <table><tr><td>2026WYTC-Hefei</td><td>RR1</td><td>U26 JAPAN</td><td>POLAND</td>
    <td><a href='/vugraph/table.php?id=1'>Watch</a></td></tr></table>
    """
    status, url = parse_vugraph_schedule(schedule, 'U26 JAPAN', 'POLAND', 1)
    assert status == 'Vugraph中継あり'
    assert url and 'id=1' in url

    archive = """
    <table><tr><td><a href='view.php?id=99'>View</a></td><td>2026WYTC-Hefei</td>
    <td>RR1</td><td>U26 JAPAN</td><td>POLAND</td></tr></table>
    """
    assert parse_vugraph_archive(archive, 'U26 JAPAN', 'POLAND', 1).endswith('view.php?id=99')


def test_history_preserves_rank_and_calculates_change(tmp_path):
    previous = TeamReport(team='U26 JAPAN', round_number=1, rank=8, rank_as_of='Round 1')
    write_snapshot([previous], tmp_path)

    current = TeamReport(team='U26 JAPAN', round_number=2, rank=6, rank_as_of='Round 2')
    apply_history([current], tmp_path)
    assert current.previous_rank == 8
    assert current.rank_change == 2

    write_snapshot([current], tmp_path)
    saved = json.loads((tmp_path / 'round-02.json').read_text(encoding='utf-8'))
    assert saved['teams'][0]['rank_change'] == 2


def test_notable_board_selection_uses_absolute_imp_first():
    boards = [
        BoardResult(1, 'N', 'None', 'sample', imp=2),
        BoardResult(2, 'E', 'N-S', 'sample', imp=-11),
        BoardResult(3, 'S', 'E-W', 'sample', imp=7, open_room=RoomResult(contract='6H N')),
    ]
    selected = select_boards(boards, limit=2)
    assert [board.board for board in selected] == [2, 3]
