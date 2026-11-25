from datetime import date

from planner.models import AccommodationFile, Constraints, OptionsFile
from planner.options import build_options, shortlist
from planner.windows import Window

BASE = {
    "horizon": {"start": "2027-01-01", "end": "2027-06-30"},
    "stay_rules": {"min_stay_days": 1, "max_stay_days": 60, "min_gap_days": 0, "max_gap_days": 0},
    "travel": {
        "route_tiers": [
            {"name": "best", "origins": ["POZ"], "destinations": ["BLQ"]},
            {"name": "third", "origins": ["WAW"], "destinations": ["BLQ"]},
        ],
        "car": {"drive_hours": 13, "min_stay_days": 1, "clear_days": 0},
    },
}
UK = {"name": "UK family visit", "airports": ["LTN", "STN"], "nights": 7}

# La Suite as in the real Travel calendar: free unless blocked.
SUITE_WITH_BLOCK = AccommodationFile.model_validate(
    {
        "accommodation": [
            {
                "name": "La Suite Elena",
                "location": "Faenza",
                "preferred": True,
                "unavailable": [{"start": "2027-02-01", "end": "2027-02-09"}],
            },
            {
                "name": "Hotel",
                "price_per_night_eur": 80,
                "available": [{"start": "2027-01-01", "end": "2027-06-30"}],
            },
        ]
    }
)


def c(**extra: object) -> Constraints:
    return Constraints.model_validate({**BASE, **extra})


def w(start: str, end: str) -> Window:
    return Window(date.fromisoformat(start), date.fromisoformat(end), ())


def fl(fid: str, d: str, orig: str, dest: str, day: str) -> dict:
    return {
        "id": fid,
        "direction": d,
        "carrier": "FR",
        "origin": orig,
        "destination": dest,
        "depart": f"{day}T10:00",
        "arrive": f"{day}T12:00",
        "price_eur": 50,
    }


NO_FLIGHTS = OptionsFile.model_validate({"options": []})


def test_blocked_dates_split_the_house_free_time() -> None:
    # Window ends during the block: house free 25 Jan to 1 Feb, Martin alone 3 nights.
    [o] = [
        x
        for x in build_options(c(), SUITE_WITH_BLOCK, NO_FLIGHTS, [w("2027-01-25", "2027-02-04")])
        if not x.martin_drives
    ]
    assert (o.house_start, o.house_end) == (date(2027, 1, 25), date(2027, 2, 1))
    assert o.solo_nights == 3 and o.solo_place.name == "Hotel"


def test_window_inside_block_is_dropped() -> None:
    assert build_options(c(), SUITE_WITH_BLOCK, NO_FLIGHTS, [w("2027-02-02", "2027-02-08")]) == []


def test_onward_trip_legs_and_no_car() -> None:
    flights = OptionsFile.model_validate(
        {
            "options": [
                fl("out", "outbound", "WAW", "BLQ", "2027-01-10"),
                fl("uk", "onward", "BLQ", "LTN", "2027-01-24"),
                fl("home", "home", "LTN", "POZ", "2027-01-31"),
            ]
        }
    )
    built = build_options(c(onward=UK), SUITE_WITH_BLOCK, flights, [w("2027-01-10", "2027-01-24")])
    assert len(built) == 1 and not built[0].martin_drives
    o = built[0]
    assert [(leg.direction, leg.day, leg.choice.id) for leg in o.legs] == [
        ("outbound", date(2027, 1, 10), "out"),
        ("onward", date(2027, 1, 24), "uk"),
        ("home", date(2027, 1, 31), "home"),
    ]
    assert [leg.tier for leg in o.legs] == [2, 1, 1]
    assert any("UK family visit for 7 nights" in p for p in o.pros)


def test_onward_flight_to_wrong_country_is_missing() -> None:
    flights = OptionsFile.model_validate(
        {
            "options": [
                fl("cdg", "onward", "BLQ", "CDG", "2027-01-24"),
            ]
        }
    )
    [o] = build_options(c(onward=UK), SUITE_WITH_BLOCK, flights, [w("2027-01-10", "2027-01-24")])
    assert o.legs[1].missing


def test_onward_drops_window_when_family_would_leave_early() -> None:
    # House blocked from 1 Feb, so the family would have to leave before Martin.
    assert (
        build_options(c(onward=UK), SUITE_WITH_BLOCK, NO_FLIGHTS, [w("2027-01-20", "2027-02-03")])
        == []
    )


def test_onward_respects_poznan_dates_during_the_uk_part() -> None:
    poz = [{"start": "2027-01-28", "end": "2027-01-28"}]
    assert (
        build_options(
            c(onward=UK, poznan_required=poz),
            SUITE_WITH_BLOCK,
            NO_FLIGHTS,
            [w("2027-01-10", "2027-01-24")],
        )
        == []
    )


def test_shortlist_still_works_with_onward() -> None:
    built = build_options(
        c(onward=UK),
        SUITE_WITH_BLOCK,
        NO_FLIGHTS,
        [w("2027-01-05", "2027-01-20"), w("2027-01-10", "2027-01-24")],
    )
    assert len(shortlist(built)) == 2
