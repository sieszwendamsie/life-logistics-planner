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
    assert any("ask for an alternative route" in c for c in o.cons)


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


TRAVEL = {
    "direct_only": True,
    "route_tiers": [
        {"name": "best", "origins": ["POZ"], "destinations": ["BLQ"]},
        {"name": "second", "origins": ["POZ"], "destinations": ["BGY"]},
    ],
    "transfer_hours": {"POZ": 0.5, "BLQ": 1, "BGY": 3},
    "car": {"drive_hours": 13, "min_stay_days": 21, "clear_days": 7},
}


def flight(fid: str, d: str, orig: str, dest: str, day: str, stops: int = 0) -> dict:
    return {
        "id": fid,
        "direction": d,
        "carrier": "X",
        "origin": orig,
        "destination": dest,
        "depart": f"{day}T08:00",
        "arrive": f"{day}T10:00",
        "price_eur": 50,
        "stops": stops,
    }


def with_travel(**extra: object) -> Constraints:
    data = CONSTRAINTS.model_dump(mode="json")
    data["travel"] = TRAVEL
    data.update(extra)
    return Constraints.model_validate(data)


def test_indirect_flights_are_ignored() -> None:
    journeys = OptionsFile.model_validate(
        {
            "options": [
                flight("via", "outbound", "POZ", "BLQ", "2027-02-01", stops=1),
                flight("r", "return", "BLQ", "POZ", "2027-02-22"),
            ]
        }
    )
    c = with_travel(travel={**TRAVEL, "car": None})
    [o] = build_options(c, PLACES, journeys, [w("2027-02-01", "2027-02-22")])
    assert [leg.missing for leg in o.legs] == [True, False]


def test_better_route_tier_wins_over_price() -> None:
    cheap_far = flight("bgy", "outbound", "POZ", "BGY", "2027-02-01") | {"price_eur": 10}
    journeys = OptionsFile.model_validate(
        {
            "options": [
                cheap_far,
                flight("blq", "outbound", "POZ", "BLQ", "2027-02-01"),
                flight("r", "return", "BGY", "POZ", "2027-02-22"),
            ]
        }
    )
    c = with_travel(travel={**TRAVEL, "car": None})
    [o] = build_options(c, PLACES, journeys, [w("2027-02-01", "2027-02-22")])
    assert o.legs[0].choice.id == "blq" and o.legs[0].tier == 1
    assert o.legs[1].tier == 2
    assert o.legs[0].hours == 0.5 + 2 + 1


def test_route_outside_tiers_is_missing() -> None:
    journeys = OptionsFile.model_validate(
        {
            "options": [
                flight("modlin", "outbound", "WMI", "BLQ", "2027-02-01"),
            ]
        }
    )
    c = with_travel(travel={**TRAVEL, "car": None})
    [o] = build_options(c, PLACES, journeys, [w("2027-02-01", "2027-02-22")])
    assert o.legs[0].missing


def test_car_option_when_no_other_travel_nearby() -> None:
    journeys = OptionsFile.model_validate(
        {
            "options": [
                flight("f1", "outbound", "POZ", "BLQ", "2027-02-01"),
                flight("f2", "return", "BLQ", "POZ", "2027-02-22"),
            ]
        }
    )
    built = build_options(with_travel(), PLACES, journeys, [w("2027-02-01", "2027-02-22")])
    car = [o for o in built if o.martin_drives]
    assert len(built) == 2 and len(car) == 1
    assert [(leg.who, leg.mode) for leg in car[0].legs] == [
        ("Martin", "car"),
        ("family", "flight"),
        ("family", "flight"),
        ("Martin", "car"),
    ]
    assert car[0].martin_hours == 26
    assert shortlist(built)[0].martin_drives


def test_no_car_near_other_travel_or_short_stay() -> None:
    near = with_travel(other_travel=[{"start": "2027-02-25", "end": "2027-02-26"}])
    built = build_options(near, PLACES, JOURNEYS, [w("2027-02-01", "2027-02-22")])
    assert not any(o.martin_drives for o in built)
    short = build_options(with_travel(), PLACES, JOURNEYS, [w("2027-02-01", "2027-02-15")])
    assert not any(o.martin_drives for o in short)


def test_cli_scenarios_compares_return_dates(capsys: pytest.CaptureFixture[str]) -> None:
    args = [
        "scenarios",
        "--constraints",
        str(EXAMPLES / "constraints.yaml"),
        "--accommodation",
        str(EXAMPLES / "accommodation.yaml"),
        "--transport",
        str(EXAMPLES / "options.yaml"),
        "--back",
        "2026-12-27=Flight A",
        "--back",
        "2027-01-03",
    ]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "Back in Poznań Sun 27 Dec 2026 (Flight A)" in out
    assert "Back in Poznań Sun 03 Jan 2027" in out
    assert "Next stay can start Sun 24 Jan to Sun 31 Jan." in out
