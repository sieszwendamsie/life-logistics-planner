from datetime import date
from pathlib import Path

import pytest

from planner.cli import main
from planner.loaders import load_accommodation, load_constraints, load_options
from planner.models import AccommodationFile, Constraints, OptionsFile
from planner.options import build_options, shortlist
from planner.windows import Window

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

CONSTRAINTS = Constraints.model_validate(
    {
        "horizon": {"start": "2027-01-01", "end": "2027-06-30"},
        "stay_rules": {
            "min_stay_days": 1,
            "max_stay_days": 60,
            "min_gap_days": 0,
            "max_gap_days": 0,
        },
        "solo_max_days": 7,
    }
)
PLACES = AccommodationFile.model_validate(
    {
        "accommodation": [
            {
                "name": "House",
                "preferred": True,
                "price_per_night_eur": 100,
                "available": [{"start": "2027-02-01", "end": "2027-02-22"}],
            },
            {
                "name": "Flat",
                "price_per_night_eur": 50,
                "available": [{"start": "2027-01-01", "end": "2027-06-30"}],
            },
        ]
    }
)
JOURNEYS = OptionsFile.model_validate(
    {
        "options": [
            {
                "id": "o1",
                "direction": "outbound",
                "carrier": "X",
                "origin": "POZ",
                "destination": "BLQ",
                "depart": "2027-02-01T08:00",
                "arrive": "2027-02-01T10:00",
                "price_eur": 40,
            },
            {
                "id": "o1b",
                "direction": "outbound",
                "carrier": "Y",
                "origin": "POZ",
                "destination": "BLQ",
                "depart": "2027-02-01T12:00",
                "arrive": "2027-02-01T15:00",
                "price_eur": 90,
            },
            {
                "id": "r1",
                "direction": "return",
                "carrier": "X",
                "origin": "BLQ",
                "destination": "POZ",
                "depart": "2027-02-22T08:00",
                "arrive": "2027-02-22T10:00",
                "price_eur": 60,
            },
        ]
    }
)


def w(start: str, end: str) -> Window:
    return Window(date.fromisoformat(start), date.fromisoformat(end), ())


def test_whole_stay_in_house_is_family_together_with_cheapest_flights() -> None:
    [o] = build_options(CONSTRAINTS, PLACES, JOURNEYS, [w("2027-02-01", "2027-02-22")])
    assert o.family_together
    assert [leg.choice.id for leg in o.legs if leg.choice] == ["o1", "r1"]
    assert o.total_cost_eur == 21 * 100 + 40 + 60
    assert o.travel_hours == 4


def test_house_free_later_means_martin_goes_first_alone() -> None:
    [o] = build_options(CONSTRAINTS, PLACES, JOURNEYS, [w("2027-01-27", "2027-02-22")])
    assert o.solo_nights == 5
    assert o.solo_place is not None and o.solo_place.name == "Flat"
    assert [(leg.who, leg.direction, leg.day) for leg in o.legs] == [
        ("Martin", "outbound", date(2027, 1, 27)),
        ("family", "outbound", date(2027, 2, 1)),
        ("everyone", "return", date(2027, 2, 22)),
    ]
    assert any("Martin alone for 5 nights" in c for c in o.cons)


def test_too_many_solo_nights_drops_the_window() -> None:
    assert build_options(CONSTRAINTS, PLACES, JOURNEYS, [w("2027-01-20", "2027-02-22")]) == []


def test_house_not_free_at_all_drops_the_window() -> None:
    assert build_options(CONSTRAINTS, PLACES, JOURNEYS, [w("2027-03-01", "2027-03-20")]) == []


def test_missing_journey_is_a_con_not_a_drop() -> None:
    [o] = build_options(CONSTRAINTS, PLACES, JOURNEYS, [w("2027-02-02", "2027-02-20")])
    assert len(o.missing_legs) == 2
    assert any("No outbound journey" in c for c in o.cons)


def test_no_preferred_place_is_an_error() -> None:
    places = AccommodationFile.model_validate({"accommodation": [{"name": "Flat"}]})
    with pytest.raises(ValueError, match="preferred"):
        build_options(CONSTRAINTS, places, JOURNEYS, [w("2027-02-01", "2027-02-22")])


def test_shortlist_prefers_complete_and_spreads_dates() -> None:
    windows = [
        w("2027-02-01", "2027-02-22"),
        w("2027-02-02", "2027-02-21"),
        w("2027-02-05", "2027-02-20"),
    ]
    built = build_options(CONSTRAINTS, PLACES, JOURNEYS, windows)
    best = shortlist(built, n=3, min_days_apart=3)
    assert [o.window.start for o in best] == [date(2027, 2, 1), date(2027, 2, 5)]


def test_example_files_give_three_options() -> None:
    c = load_constraints(EXAMPLES / "constraints.yaml")
    from planner.windows import find_windows

    built = build_options(
        c,
        load_accommodation(EXAMPLES / "accommodation.yaml"),
        load_options(EXAMPLES / "options.yaml"),
        find_windows(c),
    )
    best = shortlist(built)
    assert len(best) == 3
    assert best[0].family_together
    assert not best[0].missing_legs


def test_cli_options(capsys: pytest.CaptureFixture[str]) -> None:
    args = [
        "options",
        "--constraints",
        str(EXAMPLES / "constraints.yaml"),
        "--accommodation",
        str(EXAMPLES / "accommodation.yaml"),
        "--transport",
        str(EXAMPLES / "options.yaml"),
    ]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "Option A" in out and "Option C" in out
