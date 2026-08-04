from wyoc_tracker.html_report import _is_passed_out, validate_fixed_leads


def test_pass_with_seat_suffix_is_passed_out():
    assert _is_passed_out("Pass N")
    assert _is_passed_out("PASS E")
    assert _is_passed_out("Passed Out")
    assert _is_passed_out("All Pass")


def test_pass_with_seat_does_not_require_fixed_lead_dds():
    payload = {
        "teams": [
            {
                "team": "U21 JAPAN",
                "selected_boards": [
                    {
                        "board": 13,
                        "open_room": {"contract": "Pass N"},
                        "closed_room": None,
                        "opening_lead_dds": {},
                    }
                ],
            }
        ]
    }
    validate_fixed_leads(payload)
