from datetime import date
from pathlib import Path

from planner.cli import main
from planner.models import (
    Accommodation,
    AccommodationFile,
    Constraints,
    DateRange,
    FixedStay,
    Holiday,
    Peak,
    StayRules,
    YearPlan,
)
from planner.year import (
    _edge_only,
    build_year,
    check_year,
    holiday_blocks,
    long_weekends,
    winter_extras,
    with_bridges,
)
from planner.year_report import questions, render_year

RULES = StayRules(min_stay_days=14, max_stay_days=28, min_gap_days=14, max_gap_days=42)


def _c(**plan: object) -> Constraints:
    return Constraints(
        horizon=DateRange(start=date(2027, 1, 3), end=date(2027, 12, 31)),
        stay_rules=RULES,
        office_required=[DateRange(start=date(2027, 2, 3), end=date(2027, 2, 13))],
        holidays=[
            Holiday(day=date(2027, 1, 6), country="IT", name="Epiphany"),
            Holiday(day=date(2027, 3, 29), country="IT", name="Easter Monday"),
            Holiday(day=date(2027, 11, 1), country="IT", name="All Saints"),
            Holiday(day=date(2027, 12, 8), country="IT", name="Immaculate Conception"),
            Holiday(day=date(2027, 5, 27), country="PL", name="Corpus Christi"),
        ],
        shutdown=[
            DateRange(start=date(2026, 12, 24), end=date(2027, 1, 2)),
            DateRange(start=date(2027, 8, 13), end=date(2027, 8, 22)),
            DateRange(start=date(2027, 12, 24), end=date(2028, 1, 2)),
        ],
        year_plan=YearPlan(
            year=2027,
            start=date(2027, 1, 3),
            fixed_stays=[FixedStay(start=date(2027, 1, 31), end=date(2027, 2, 28))],
            peaks=[Peak(start=date(2027, 6, 26), end=date(2027, 8, 31), name="PL summer")],
            **plan,
        ),
    )


ACC = AccommodationFile(
    accommodation=[
        Accommodation(
            name="La Suite",
            preferred=True,
            unavailable=[DateRange(start=date(2027, 4, 9), end=date(2027, 4, 11))],
        )
    ]
)


def test_holiday_costs_only_working_days() -> None:
    c = _c()
    # Sat 23 Oct to Sun 7 Nov: 10 weekdays, minus All Saints (Mon 1 Nov) = 9 paid.
    [b] = [
        b
        for b in holiday_blocks(c, c.year_plan, date(2027, 10, 20), date(2027, 11, 10), 16, 16)
        if b.start == date(2027, 10, 23)
    ]
    assert (b.days, b.paid_days, b.it_holidays) == (16, 9, ("All Saints",))


def test_polish_holidays_are_not_free() -> None:
    c = _c()
    [b] = [
        b
        for b in holiday_blocks(c, c.year_plan, date(2027, 5, 26), date(2027, 5, 31), 4, 4)
        if b.start == date(2027, 5, 27)
    ]
    assert b.paid_days == 2  # Thu Corpus Christi and Fri both cost pay


def test_long_holiday_wraps_the_summer_shutdown_and_prefers_september() -> None:
    r = build_year(_c(), ACC)
    long = r.long_pick
    assert long and long.start <= date(2027, 8, 13) and long.end >= date(2027, 8, 22)
    assert 28 <= long.days <= 31 and long.paid_days == 14
    # Same pay, fewer school-holiday days: the one reaching into September wins.
    assert long.start == date(2027, 8, 7)


def test_second_holiday_is_far_from_the_long_one_and_cheapest() -> None:
    r = build_year(_c(), ACC)
    s = r.second_pick
    assert s and s.paid_days == 9 and s.days == 16
    assert abs((s.start - r.long_pick.start).days) >= 42


def test_pinned_holiday_is_used() -> None:
    r = build_year(_c(long_holiday_start=date(2027, 7, 31)), ACC)
    assert r.long_pick and r.long_pick.start == date(2027, 7, 31)


def test_long_weekends_and_winter_extras() -> None:
    c = _c()
    weekends = long_weekends(c, c.year_plan, [])
    easter = [b for b in weekends if "Easter Monday" in b.it_holidays]
    assert [(b.days, b.paid_days) for b in easter] == [(3, 0), (4, 1), (5, 2)]
    dec = [b for b in weekends if "Immaculate Conception" in b.it_holidays]
    assert dec and dec[0].paid_days == 2  # Wednesday: two bridge days
    winter = winter_extras(c, c.year_plan)
    assert winter and all(0 < b.paid_days <= 2 for b in winter)
    assert any(b.start == date(2027, 12, 23) and b.paid_days == 1 for b in winter)


def test_stays_follow_the_rules() -> None:
    c = _c()
    r = build_year(c, ACC)
    stays = r.stays
    assert stays and stays[0].fixed and stays[0].start == date(2027, 1, 31)
    for a, b in zip(stays, stays[1:], strict=False):
        assert a.end <= b.start
    for st in stays[1:]:
        assert r.plan.min_stay_nights <= st.nights <= r.plan.max_stay_nights
        assert c.day_off(st.start) and c.day_off(st.end)
        assert st.blocked_nights <= c.solo_max_days
        for h in r.holidays:
            assert st.end < h.start or h.end < st.start
        assert not any(s.start <= st.start <= s.end for s in c.shutdown)


def test_missing_italian_holiday_becomes_a_question() -> None:
    c = _c()
    r = build_year(c, ACC)
    assert any("Republic Day" in q for q in questions(c, r))
    html = render_year(c, r)
    assert "Stays in Faenza" in html and "Republic Day" in html


def test_cli_year_writes_page(tmp_path: Path) -> None:
    out = tmp_path / "year.html"
    code = main(
        [
            "year",
            "--constraints",
            "examples/constraints.yaml",
            "--accommodation",
            "examples/accommodation.yaml",
            "--out",
            str(out),
        ]
    )
    assert code == 0 and out.exists()


def test_preferred_poland_event_pushes_stays_away() -> None:
    from planner.models import Presence

    c = _c()
    base = build_year(c, ACC).stays
    second = base[1]
    wish = Presence(
        title="Birthday",
        start=second.start + (second.end - second.start) / 2,
        end=second.start + (second.end - second.start) / 2,
        where="PL",
        who=["Martin", "Paula", "Basia"],
        strength="pref",
    )
    moved = build_year(c.model_copy(update={"presence": [wish]}), ACC).stays
    assert all(not (st.start <= wish.start <= st.end) for st in moved)


def test_second_holiday_months_and_pin() -> None:
    r = build_year(_c(second_holiday_months=[3, 4]), ACC)
    assert r.second_options and all(b.start.month in (3, 4) for b in r.second_options)
    r = build_year(_c(second_holiday_months=[3, 4], second_holiday_start=date(2027, 3, 6)), ACC)
    assert r.second_pick and (r.second_pick.start, r.second_pick.end) == (
        date(2027, 3, 6),
        date(2027, 3, 21),
    )
    assert r.second_pick.paid_days == 10
    assert all(st.end < date(2027, 3, 6) or st.start > date(2027, 3, 21) for st in r.stays)


def test_free_days_off_cover_long_weekends_and_shutdowns() -> None:
    from planner.year_report import free_days_off

    free = free_days_off(_c(), 2027)
    # Easter Monday: Sat 27 to Mon 29 Mar; All Saints: Sat 30 Oct to Mon 1 Nov.
    assert {date(2027, 3, 27), date(2027, 3, 28), date(2027, 3, 29)} <= set(free)
    assert {date(2027, 10, 30), date(2027, 10, 31), date(2027, 11, 1)} <= set(free)
    assert date(2027, 3, 26) not in free  # Good Friday is a working day
    # A midweek holiday alone; the shutdown with its weekends.
    assert date(2027, 12, 8) in free and date(2027, 12, 7) not in free
    assert date(2027, 1, 3) in free and date(2027, 8, 22) in free
    assert date(2027, 3, 6) not in free  # a plain weekend


def test_rhythm_follows_remote_share() -> None:
    r = build_year(_c(remote_share=(0.55, 0.65)), ACC)
    assert r.workdays and 0.55 <= r.remote_share <= 0.65
    office = sum(
        1
        for st in r.stays
        for i in range(1, st.nights)
        if not _c().day_off(st.start + __import__("datetime").timedelta(days=i))
    )
    assert office >= r.office_days  # holidays never fall inside a stay


def test_check_year_passes_for_a_good_plan() -> None:
    from planner.year import check_year

    c = _c(second_holiday_months=[3, 4])
    r = build_year(c, ACC)
    assert check_year(c, r) == []


def test_check_year_reports_broken_rules() -> None:
    from planner.year import check_year

    c = _c(second_holiday_months=[3])
    r = build_year(c, ACC)
    r.plan = r.plan.model_copy(update={"remote_share": (0.9, 0.95), "second_holiday_months": [11]})
    problems = " ".join(check_year(c, r))
    assert "Remote share" in problems
    assert "Second holiday starts in month" in problems
    r.long_pick = None
    assert "No long holiday" in " ".join(check_year(c, r))


def test_options_compare_bridges_and_holidays() -> None:
    from planner.models import YearOption
    from planner.year import build_options
    from planner.year_report import render_options

    opts = [
        YearOption(label="A", second_holiday_start=date(2027, 3, 6)),
        YearOption(
            label="B",
            second_holiday_start=date(2027, 3, 6),
            # Thu + Fri after Wed 8 Dec make a 5-day break; a Saturday is ignored.
            bridge_days=[date(2027, 12, 9), date(2027, 12, 10), date(2027, 12, 11)],
        ),
    ]
    c = _c(second_holiday_months=[3, 4], options=opts)
    a, b = build_options(c, ACC)
    assert (a.label, b.label) == ("A", "B")
    assert b.bridges == [date(2027, 12, 9), date(2027, 12, 10)]
    assert b.paid_days_off == a.paid_days_off + 2
    dec = [x for x in b.breaks if x.start <= date(2027, 12, 8) <= x.end]
    assert dec and (dec[0].start, dec[0].end) == (date(2027, 12, 8), date(2027, 12, 12))
    assert b.days_off_in_breaks == a.days_off_in_breaks + 5
    cb = with_bridges(c, b.bridges)
    for st in b.stays:  # a bridge day only in the long weekend next to travel
        assert _edge_only(cb, st.start, st.end, frozenset(b.bridges))
    html = render_options(c, [a, b])
    assert "Bridge day, paid" in html and "Side by side" in html


def test_no_holiday_periods_are_respected() -> None:
    quiet = [
        DateRange(start=date(2027, 1, 1), end=date(2027, 2, 28)),
        DateRange(start=date(2027, 9, 15), end=date(2027, 12, 31)),
    ]
    r = build_year(_c(no_holiday=quiet), ACC)
    for b in r.second_options + r.long_options:
        assert not any(b.start <= q.end and q.start <= b.end for q in quiet)
    # A pinned holiday inside a quiet period is refused, so none lands there.
    from planner.year import check_year

    c = _c(no_holiday=quiet, second_holiday_start=date(2027, 10, 23))
    assert not any("no-holiday" in p for p in check_year(c, build_year(c, ACC)))


def test_long_weekend_joins_a_stay_only_next_to_travel() -> None:
    c = with_bridges(_c(), [date(2027, 12, 9), date(2027, 12, 10)])  # Wed 8 Dec to Sun 12
    br = frozenset([date(2027, 12, 9), date(2027, 12, 10)])
    # Ends on Sun 12 Dec after the long weekend in Faenza: fine.
    assert _edge_only(c, date(2027, 11, 21), date(2027, 12, 12), br)
    # Starts on Wed 8 Dec, spending the long weekend in Faenza first: fine.
    assert _edge_only(c, date(2027, 12, 8), date(2027, 12, 23), br)
    # Long weekend in the middle, with working days on both sides: not allowed.
    assert not _edge_only(c, date(2027, 12, 4), date(2027, 12, 19), br)


def test_check_year_caps_long_weekends_in_faenza() -> None:
    r = build_year(_c(trip_long_weekends=0), ACC)
    assert r.stays
    r.stays[0].long_weekends = ["08 Dec-12 Dec"]
    assert any("long weekends are joined" in p for p in check_year(_c(trip_long_weekends=0), r))


def test_print_sheets_have_calendar_and_summary_per_option() -> None:
    from planner.models import YearOption
    from planner.year import build_options
    from planner.year_report import render_options

    opts = [YearOption(label="A"), YearOption(label="B", bridge_days=[date(2027, 12, 9)])]
    c = _c(options=opts)
    html = render_options(c, build_options(c, ACC), "year_print.html.j2")
    assert html.count('class="sheet"') == 4  # front and back for each option
    assert "A4 landscape" in html and "B: summary" in html


def test_long_weekends_anywhere_allows_a_bridge_inside_a_stay() -> None:
    from planner.models import YearOption
    from planner.year import build_options

    # Bridge days on every Thursday-Friday of May: only allowed inside a stay if the
    # option says long weekends may fall anywhere in it.
    may = [date(2027, 5, d) for d in (6, 7, 13, 14, 20, 21)]
    strict, loose = build_options(
        _c(
            options=[
                YearOption(label="edge", bridge_days=may, trip_long_weekends=9),
                YearOption(
                    label="any", bridge_days=may, trip_long_weekends=9, long_weekends_anywhere=True
                ),
            ]
        ),
        ACC,
    )
    cb = with_bridges(_c(), may)
    for st in strict.stays:
        assert _edge_only(cb, st.start, st.end, frozenset(may))
    assert loose.plan.long_weekends_anywhere and not strict.plan.long_weekends_anywhere


def test_options_page_shows_estimated_costs_when_given() -> None:
    from planner.models import YearOption
    from planner.year import build_options
    from planner.year_report import render_options

    c = _c(options=[YearOption(label="A")])
    (r,) = build_options(c, ACC)
    st = r.stays[0]
    row = {
        "start": st.start.isoformat(),
        "la_suite": 100,
        "elsewhere": 0,
        "car": 400,
        "flights": 0,
        "missing": ["out", "back"],
        "out": None,
        "back": None,
    }
    costs = {
        "checked": "today",
        "la_suite_eur_per_night": 50,
        "notes": ["note one"],
        "short_note": "short",
        "options": {"A": [row]},
    }
    html = render_options(c, [r], costs=costs)
    assert "Estimated cost of Faenza trips" in html and "€500*" in html and "note one" in html
    assert "Estimated cost" not in render_options(c, [r])


def test_celebration_days_are_marked_like_a_holiday() -> None:
    from planner.models import Presence
    from planner.year_report import _months

    c = _c()
    c.presence = [
        Presence(
            title="Communion",
            start=date(2027, 5, 15),
            end=date(2027, 5, 15),
            where="PL",
            who=["Martin"],
            strength="must",
        ),
        Presence(
            title="Maybe",
            start=date(2027, 5, 22),
            end=date(2027, 5, 22),
            where="PL",
            who=["Martin"],
            strength="pref",
        ),
    ]
    r = build_year(c, ACC)
    may = next(cells for name, cells, _ in _months(c, r) if name == "May")
    day15, day22 = may[14], may[21]
    assert "Communion" in day15.title
    assert day15.kind == "holiday" or day15.off
    assert "Maybe" not in day22.title


def test_max_trips_caps_the_number_of_stays() -> None:
    free = build_year(_c(), ACC)
    capped = build_year(_c(max_trips=4, away_nights=(14, 42)), ACC)
    assert capped.stays and capped.trips <= 4
    assert capped.trips <= free.trips
