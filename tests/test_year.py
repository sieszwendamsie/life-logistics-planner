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
from planner.year import build_year, holiday_blocks, long_weekends, winter_extras
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
        assert 14 <= st.nights <= 21
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
