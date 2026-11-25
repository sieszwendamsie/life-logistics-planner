from datetime import date, datetime
from pathlib import Path

import pytest

from planner.cli import main
from planner.costs import round_trip
from planner.loaders import load_accommodation, load_constraints, load_options
from planner.models import (
    AccommodationFile,
    CarCosts,
    Constraints,
    OptionsFile,
    TransportOption,
)
from planner.options import Leg, build_options, shortlist
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
    assert o.total_cost_eur == 21 * 100 + 2 * (40 + 60)  # 2 seats, Basia on Paula's lap
    assert o.travel_hours == 8  # each way: 1.5 h at the airport, 2 h flight, 0.5 h after


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
    "car": {"drive_hours": 13, "min_stay_days": 21, "clear_days": 7, "days_off_only": False},
    "infant_fee_eur": {"X": 25, "Y": 25},
    "checked_bag_eur": {"X": 40, "Y": 40},
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
                flight("r", "return", "BGY", "POZ", "2027-02-22")
                | {"depart": "2027-02-22T12:00", "arrive": "2027-02-22T14:00"},
            ]
        }
    )
    c = with_travel(travel={**TRAVEL, "car": None})
    [o] = build_options(c, PLACES, journeys, [w("2027-02-01", "2027-02-22")])
    assert o.legs[0].choice.id == "blq" and o.legs[0].tier == 1
    assert o.legs[1].tier == 2
    assert o.legs[0].hours == 0.5 + 1.5 + 2 + 0.5 + 1  # home, airport wait, flight, bags, home


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
    # Driving costs are in the total; the flying option has no hire car by default.
    fly = next(o for o in built if not o.martin_drives)
    drive_cost = round_trip(CarCosts(), date(2027, 2, 1), date(2027, 2, 22)).total_eur
    assert car[0].total_cost_eur == pytest.approx(
        # Martin's two seats are gone, and the luggage goes in the car: no 4 bags at €40.
        fly.total_cost_eur - 100 - 4 * 40 + drive_cost
    )  # Martin drives, no seat
    assert any("Driving there and back" in x for x in car[0].cons)
    # Basia on Paula's lap: infant fee each flight. Bags only when nobody drives.
    assert car[0].costs["Infant fees"] == 2 * 25 and "Checked bags" not in car[0].costs
    assert fly.costs["Checked bags"] == 2 * 2 * 40


def test_ground_costs_only_from_live_checks() -> None:
    def ground(gid: str, kind: str, start: str, end: str | None, price: float) -> dict:
        return {
            "id": gid,
            "kind": kind,
            "start": start,
            "end": end,
            "price_eur": price,
            "checked_on": "2026-11-25",
        }

    flights = [
        flight("f1", "outbound", "POZ", "BGY", "2027-02-01"),
        flight("f2", "return", "BGY", "POZ", "2027-02-22")
        | {"depart": "2027-02-22T12:00", "arrive": "2027-02-22T14:00"},
    ]
    c = with_travel(travel={**TRAVEL, "car": None})
    win = [w("2027-02-01", "2027-02-22")]
    # No hire-car quote yet: not a proposal, nothing guessed in the total.
    [o] = build_options(c, PLACES, OptionsFile.model_validate({"options": flights}), win)
    assert o.open_ground == 1
    assert any("Hire car 01 Feb to 22 Feb: price not checked live yet" in x for x in o.cons)
    # A checked quote for exactly those days is added to the total.
    quote = ground("h", "car_hire", "2027-02-01", "2027-02-22", 200)
    journeys = OptionsFile.model_validate({"options": flights, "ground": [quote]})
    [o2] = build_options(c, PLACES, journeys, win)
    assert o2.open_ground == 0 and o2.total_cost_eur == o.total_cost_eur + 200
    # A quote for another drop-off airport does not fit these flights (BGY in and out).
    wrong = quote | {"id": "w", "pick_up": "BGY", "drop_off": "BLQ", "price_eur": 50}
    right = quote | {"id": "r", "pick_up": "BGY", "drop_off": "BGY", "price_eur": 300}
    journeys = OptionsFile.model_validate({"options": flights, "ground": [wrong, right]})
    [o3] = build_options(c, PLACES, journeys, win)
    assert o3.costs["Car hire"] == 300


def test_martin_alone_into_bologna_takes_the_train() -> None:
    from planner.options import _ground

    c = with_travel(travel={**TRAVEL, "car": None})
    out = TransportOption.model_validate(
        flight("m", "outbound", "WAW", "BLQ", "2027-02-01") | {"checked_on": "2026-11-25"}
    )
    legs = [Leg("Martin", "outbound", date(2027, 2, 1), choice=out)]
    found = _ground(
        c,
        OptionsFile(options=[]),
        legs,
        w("2027-02-01", "2027-02-22"),
        date(2027, 2, 6),
        date(2027, 2, 22),
    )
    labels = [label for _, label in found]
    assert labels == [
        "Hire car 06 Feb to 22 Feb",
        "Martin: train from BLQ",
        "Martin: train to collect the hire car",
    ]


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


def test_unchecked_flight_is_a_con() -> None:
    [o] = build_options(CONSTRAINTS, PLACES, JOURNEYS, [w("2027-02-01", "2027-02-22")])
    assert any("not checked live yet" in c for c in o.cons)


def test_far_airport_needs_a_checked_bus_or_train() -> None:
    out = flight("ber", "outbound", "BER", "BLQ", "2027-02-01") | {
        "depart": "2027-02-01T13:45",
        "arrive": "2027-02-01T15:30",
    }
    travel = {
        **TRAVEL,
        "car": None,
        "route_tiers": [{"name": "far", "origins": ["BER", "POZ"], "destinations": ["BLQ"]}],
    }
    c = with_travel(travel=travel)
    win = [w("2027-02-01", "2027-02-22")]
    back = flight("r", "return", "BLQ", "POZ", "2027-02-22")

    def bus(gid: str, dep: str, arr: str) -> dict:
        return {
            "id": gid,
            "kind": "transfer",
            "airport": "BER",
            "start": "2027-02-01",
            "depart": f"2027-02-01T{dep}",
            "arrive": f"2027-02-01T{arr}",
            "price_eur": 20,
            "checked_on": "2026-11-25",
        }

    # No bus checked yet: the option is not a proposal.
    [o] = build_options(c, PLACES, OptionsFile.model_validate({"options": [out, back]}), win)
    assert o.legs[0].open_transfer and o.open_ground >= 1
    # Too early (before 05:00) or too late (less than 2 h before take-off): still open.
    late = {
        "options": [out, back],
        "ground": [bus("a", "04:00", "07:20"), bus("b", "09:00", "13:00")],
    }
    [o] = build_options(c, PLACES, OptionsFile.model_validate(late), win)
    assert o.legs[0].open_transfer
    # A bus leaving 06:00 and arriving 09:20 fits; door to door counts from 06:00.
    ok = {"options": [out, back], "ground": [bus("c", "06:00", "09:20")]}
    [o] = build_options(c, PLACES, OptionsFile.model_validate(ok), win)
    assert o.legs[0].transfer.id == "c"
    assert o.legs[0].hours == 9.5 + 0.5 + 1  # bus 06:00 to landing 15:30, bags, BLQ to home


def test_flight_bag_price_beats_airline_table() -> None:
    journeys = OptionsFile.model_validate(
        {
            "options": [
                flight("f1", "outbound", "POZ", "BLQ", "2027-02-01") | {"bag_eur": 10},
                flight("f2", "return", "BLQ", "POZ", "2027-02-22"),
            ]
        }
    )
    c = with_travel(travel={**TRAVEL, "car": None})
    [o] = build_options(c, PLACES, journeys, [w("2027-02-01", "2027-02-22")])
    # Out: 2 adults x €10 (this flight); back: 2 adults x €40 (airline table).
    assert o.costs["Checked bags"] == 2 * 10 + 2 * 40


def test_family_window_drops_too_early_or_too_late_flights() -> None:
    # Return BGY 08:00: leaving Faenza at 03:30 breaks the 05:00 limit.
    # Return BLQ 14:00 (from WRO, relative's lift 2 h): home 17:30, fine.
    journeys = OptionsFile.model_validate(
        {
            "options": [
                flight("out", "outbound", "POZ", "BLQ", "2027-02-01"),
                flight("early", "return", "BGY", "POZ", "2027-02-22"),
                flight("ok", "return", "BLQ", "WRO", "2027-02-22")
                | {"depart": "2027-02-22T14:00", "arrive": "2027-02-22T15:00"},
            ]
        }
    )
    travel = {
        **TRAVEL,
        "car": None,
        "route_tiers": [
            *TRAVEL["route_tiers"],
            {"name": "far", "origins": ["WRO"], "destinations": ["BLQ"]},
        ],
        "family_lifts": {"WRO": {"hours": 2, "km": 200, "toll_eur": 10}},
        "pl_fuel_eur_per_l": 1.5,
    }
    c = with_travel(travel=travel)
    [o] = build_options(c, PLACES, journeys, [w("2027-02-01", "2027-02-22")])
    back = o.legs[1]
    assert back.choice.id == "ok"
    assert not back.open_transfer  # the relative drives them, no bus needed
    j = o.journeys[1]
    assert "lift" in j.how
    assert j.leave == datetime(2027, 2, 22, 11, 30)  # 14:00 - 1.5 h - 1 h to BLQ
    assert j.arrive == datetime(2027, 2, 22, 17, 30)  # 15:00 + 0.5 h + 2 h lift
    # The relative drives there and back: 2 x (200 km x 6 l/100 km x €1.50 + €10 toll).
    assert o.costs["Lifts by relatives in Poland: fuel, tolls"] == 2 * (200 * 0.06 * 1.5 + 10)


def test_family_flight_too_late_is_not_used() -> None:
    late = flight("late", "outbound", "POZ", "BGY", "2027-02-01") | {
        "depart": "2027-02-01T15:30",
        "arrive": "2027-02-01T17:30",
    }  # + 0.5 h bags + 3 h drive = 21:00, after 20:00
    journeys = OptionsFile.model_validate(
        {"options": [late, flight("r", "return", "BLQ", "POZ", "2027-02-22")]}
    )
    c = with_travel(travel={**TRAVEL, "car": None})
    [o] = build_options(c, PLACES, journeys, [w("2027-02-01", "2027-02-22")])
    assert o.legs[0].missing
