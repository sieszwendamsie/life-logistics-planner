from datetime import date

from planner.models import AccommodationFile, Constraints, OptionsFile
from planner.options import build_options
from planner.windows import Window, find_windows

BASE = {
    "horizon": {"start": "2027-01-01", "end": "2027-06-30"},
    "last_return": "2027-01-01",
    "stay_rules": {
        "min_stay_days": 21,
        "max_stay_days": 21,
        "min_gap_days": 28,
        "max_gap_days": 30,
    },
}
SUITE = AccommodationFile.model_validate(
    {
        "accommodation": [
            {"name": "La Suite Elena", "preferred": True, "price_per_night_eur": 100},
            {"name": "Hotel", "price_per_night_eur": 80},
        ]
    }
)
NO_FLIGHTS = OptionsFile.model_validate({"options": []})


def c(*presence: dict) -> Constraints:
    return Constraints.model_validate({**BASE, "presence": list(presence)})


def p(start: str, end: str, where: str, who: list[str], strength: str = "must") -> dict:
    return {
        "title": "test",
        "start": start,
        "end": end,
        "where": where,
        "who": who,
        "strength": strength,
    }


def test_martin_must_in_poland_blocks_windows() -> None:
    # Windows start 29-31 Jan and last 21 days; a PL event on 15 Feb blocks all of them.
    assert find_windows(c(p("2027-02-15", "2027-02-15", "PL", ["Martin"]))) == []


def test_martin_must_in_italy_counts_as_office() -> None:
    windows = find_windows(c(p("2027-02-19", "2027-02-20", "IT", ["Martin"])))
    assert windows and all(w.end >= date(2027, 2, 20) for w in windows)
    assert all(len(w.office_covered) == 1 for w in windows)


def test_family_appointment_means_martin_goes_first_and_stays_in_the_house() -> None:
    con = c(p("2027-01-30", "2027-01-31", "PL", ["Basia"]))
    w = Window(date(2027, 1, 29), date(2027, 2, 19), ())
    [o] = build_options(con, SUITE, NO_FLIGHTS, [w])
    assert o.house_start == date(2027, 2, 1)
    assert o.solo_nights == 3
    assert o.solo_place is None  # Martin is alone at La Suite, no hotel needed
    assert o.total_cost_eur == 21 * 100
    assert any("3 at La Suite Elena" in x for x in o.cons)


def test_long_family_appointment_drops_the_window() -> None:
    con = c(p("2027-01-29", "2027-02-10", "PL", ["Paula", "Basia"]))
    w = Window(date(2027, 1, 29), date(2027, 2, 19), ())
    assert build_options(con, SUITE, NO_FLIGHTS, [w]) == []


def test_preferred_event_is_only_a_con() -> None:
    con = c(p("2027-02-05", "2027-02-05", "PL", ["Martin"], strength="pref"))
    assert find_windows(con)
    w = Window(date(2027, 1, 29), date(2027, 2, 19), ())
    [o] = build_options(con, SUITE, NO_FLIGHTS, [w])
    assert any("Misses 'test'" in x for x in o.cons)


def test_flex_and_any_are_ignored() -> None:
    con = c(
        p("2027-02-05", "2027-02-05", "PL", ["Martin"], strength="flex"),
        p("2027-02-06", "2027-02-06", "any", ["Martin"]),
    )
    assert len(find_windows(con)) == 3
