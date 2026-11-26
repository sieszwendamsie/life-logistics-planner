from datetime import date

from planner.holidays import long_weekends, peak_days
from planner.models import AccommodationFile, Constraints, Holiday, OptionsFile
from planner.options import build_options
from planner.windows import Window, find_windows


def test_monday_holiday_makes_a_long_weekend() -> None:
    # Easter Monday 29 Mar 2027: Sat 27 to Mon 29.
    [lw] = long_weekends([Holiday(day=date(2027, 3, 29), country="PL", name="Easter Monday")])
    assert (lw.start, lw.end) == (date(2027, 3, 27), date(2027, 3, 29))
    assert date(2027, 3, 26) in lw.peak_days()  # the Friday before


def test_thursday_holiday_bridges_to_the_weekend() -> None:
    # Corpus Christi Thu 27 May 2027: Thu to Sun with Friday as a bridge day.
    [lw] = long_weekends([Holiday(day=date(2027, 5, 27), country="PL", name="Corpus Christi")])
    assert (lw.start, lw.end) == (date(2027, 5, 27), date(2027, 5, 30))


def test_midweek_holiday_alone_is_not_a_long_weekend() -> None:
    assert long_weekends([Holiday(day=date(2027, 6, 2), country="IT")]) == []  # Wednesday


def test_countries_are_separate() -> None:
    hs = [Holiday(day=date(2027, 4, 26), country="IT")]  # Monday
    assert set(peak_days(hs)) == {
        date(2027, 4, 23),
        date(2027, 4, 24),
        date(2027, 4, 25),
        date(2027, 4, 26),
    }


BASE = {
    "horizon": {"start": "2027-01-01", "end": "2027-06-30"},
    "stay_rules": {"min_stay_days": 1, "max_stay_days": 60, "min_gap_days": 0, "max_gap_days": 0},
    "travel": {"route_tiers": [{"name": "POZ-BGY", "origins": ["POZ"], "destinations": ["BGY"]}]},
}
HOUSE = AccommodationFile.model_validate({"accommodation": [{"name": "House", "preferred": True}]})


def _flight(fid: str, d: str, day: str, at: str, arr: str) -> dict:
    o, dst = ("POZ", "BGY") if d == "outbound" else ("BGY", "POZ")
    return {
        "id": fid,
        "direction": d,
        "carrier": "FR",
        "origin": o,
        "destination": dst,
        "depart": f"{day}T{at}",
        "arrive": f"{day}T{arr}",
        "price_eur": 50,
        "checked_on": "2026-11-25",
    }


def test_family_flight_moves_to_the_weekend_in_good_hours() -> None:
    c = Constraints.model_validate(
        {**BASE, "travel": {**BASE["travel"], "car": {"min_stay_days": 1, "days_off_only": False}}}
    )
    flights = OptionsFile.model_validate(
        {
            "options": [
                _flight("thu", "outbound", "2027-02-11", "12:40", "14:30"),
                _flight("sat", "outbound", "2027-02-13", "12:40", "14:30"),
                _flight("sun-early", "return", "2027-02-28", "05:45", "07:30"),
                _flight("mon", "return", "2027-03-01", "12:00", "14:00"),
            ]
        }
    )
    w = Window(date(2027, 2, 9), date(2027, 3, 2), ())
    drive = next(o for o in build_options(c, HOUSE, flights, [w]) if o.martin_drives)
    out = next(g for g in drive.legs if g.who == "family" and g.direction == "outbound")
    back = next(g for g in drive.legs if g.who == "family" and g.direction == "return")
    assert out.choice and out.choice.id == "sat"
    assert back.choice and back.choice.id == "sun-early"  # weekend beats good hours
    assert any("outside 10:00-18:00" in x for x in drive.cons)
    assert any("rather not shift" in x for x in drive.cons)
    assert (drive.family_start, drive.family_end) == (date(2027, 2, 13), date(2027, 2, 28))


def test_holidays_in_italy_and_long_weekend_flights_are_cons() -> None:
    c = Constraints.model_validate(
        {
            **BASE,
            "holidays": [
                {"day": "2027-03-29", "country": "PL", "name": "Easter Monday"},
                {"day": "2027-03-10", "country": "IT", "name": "Test"},
            ],
        }
    )
    w = Window(date(2027, 3, 1), date(2027, 3, 29), ())
    [o] = [o for o in build_options(c, HOUSE, OptionsFile(options=[]), [w])]
    assert any("public holidays: 10 Mar (IT Test)" in x for x in o.cons)
    assert any("long weekend in PL" in x for x in o.cons)
    assert o.soft >= 2


def test_leave_blocks_a_stay() -> None:
    c = Constraints.model_validate(
        {
            **BASE,
            "stay_rules": {**BASE["stay_rules"], "min_stay_days": 20, "max_stay_days": 20},
            "leave": [{"start": "2027-02-10", "end": "2027-02-12"}],
        }
    )
    assert all(not (w.start <= date(2027, 2, 11) < w.end) for w in find_windows(c))


def test_car_only_on_days_off() -> None:
    c = Constraints.model_validate(
        {
            **BASE,
            "travel": {**BASE["travel"], "car": {"min_stay_days": 1}},
            "holidays": [
                {"day": "2027-03-29", "country": "IT", "name": "Easter Monday"},
                {"day": "2027-05-03", "country": "PL", "name": "Constitution Day"},
            ],
        }
    )
    no_flights = OptionsFile(options=[])

    def drives(start: str, end: str) -> bool:
        w = Window(date.fromisoformat(start), date.fromisoformat(end), ())
        return any(o.martin_drives for o in build_options(c, HOUSE, no_flights, [w]))

    assert not drives("2027-02-09", "2027-03-02")  # Tuesday to Tuesday
    assert drives("2027-03-06", "2027-03-29")  # Saturday to Easter Monday (office closed)
    # A Polish holiday is a normal paid working day for Martin: no driving.
    assert not drives("2027-04-10", "2027-05-03")


def test_martin_flying_on_a_working_day_is_a_con() -> None:
    c = Constraints.model_validate(BASE)
    flights = OptionsFile.model_validate(
        {"options": [_flight("tue", "outbound", "2027-02-09", "12:00", "14:00")]}
    )
    w = Window(date(2027, 2, 9), date(2027, 2, 13), ())
    [o] = build_options(c, HOUSE, flights, [w])
    assert any("Martin flies on a working day (Tue 09 Feb)" in x for x in o.cons)
