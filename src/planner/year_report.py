"""Draw the year plan (`planner year --out ...`) as one HTML page.

The maths lives in planner.year; this module only turns it into rows of days
for the template templates/year.html.j2.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from jinja2 import Environment, PackageLoader, select_autoescape

from planner.models import Constraints
from planner.year import Block, Stay, YearResult


@dataclass
class Cell:
    day: int
    kind: str  # home, stay, solo, holiday, shutdown, empty
    weekend: bool
    it: bool  # Italian public holiday
    pl: bool  # Polish public holiday
    title: str
    off: bool = False  # a free day off inside a Faenza stay (outlined in holiday colour)


def _span(a: date, b: date) -> list[date]:
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def free_days_off(c: Constraints, year: int) -> dict[date, str]:
    """Days off that cost nothing beyond weekends: shutdowns and Italian holidays on
    a weekday, each with the whole run of free days around it (a long weekend)."""
    seeds: dict[date, str] = {}
    for s in c.shutdown:
        d = s.start
        while d <= s.end:
            seeds[d] = "Shutdown (office closed)"
            d += timedelta(days=1)
    for h in c.holidays:
        if h.country == "IT" and h.day.weekday() < 5:
            seeds.setdefault(h.day, f"Italian holiday: {h.name}" if h.name else "Italian holiday")
    leave = {d for r in c.leave for d in _span(r.start, r.end)}
    # Mark every run of days off (weekends included) that holds such a day.
    days: dict[date, str] = {}
    d = date(year, 1, 1) - timedelta(days=14)
    last = date(year, 12, 31) + timedelta(days=14)
    while d <= last:
        if not c.day_off(d):
            d += timedelta(days=1)
            continue
        run = []
        while c.day_off(d):
            run.append(d)
            d += timedelta(days=1)
        why = next((seeds[x] for x in run if x in seeds), None)
        if why is None:
            continue
        for x in run:
            if x.year == year:
                if x in leave:
                    days[x] = f"Bridge day, paid ({why})"
                else:
                    days[x] = seeds.get(x) or f"Long weekend ({why})"
    return days


def _kind(c: Constraints, r: YearResult, d: date, free: dict[date, str]) -> tuple[str, str]:
    for st in r.stays:
        if st.start <= d <= st.end:
            label = f"Faenza {st.start:%d %b} to {st.end:%d %b}"
            if d in (st.start, st.end):
                label += " (travel day)"
            if d in free:
                label += f" · {free[d]}"
            return ("solo" if _blocked(st, d) else "stay"), label
    for b in r.holidays:
        if b.start <= d <= b.end:
            return "holiday", f"Holiday {b.start:%d %b} to {b.end:%d %b}"
    if d in free:
        return "holiday", free[d]
    return "home", "Poznań"


def _blocked(st: Stay, d: date) -> bool:
    return d in st.blocked


def _months(c: Constraints, r: YearResult) -> list[tuple[str, list[Cell]]]:
    it = {h.day: h.name for h in c.holidays if h.country == "IT"}
    pl = {h.day: h.name for h in c.holidays if h.country == "PL"}
    free = free_days_off(c, r.plan.year)
    rows = []
    for m in range(1, 13):
        first = date(r.plan.year, m, 1)
        cells = []
        d = first
        while d.month == m:
            kind, title = _kind(c, r, d, free)
            extra = [f"IT: {it[d]}" for _ in [0] if d in it] + [
                f"PL: {pl[d]}" for _ in [0] if d in pl
            ]
            cells.append(
                Cell(
                    day=d.day,
                    kind=kind,
                    weekend=d.weekday() >= 5,
                    it=d in it,
                    pl=d in pl,
                    title=f"{d:%a %d %b}: {title}" + (f" · {' · '.join(extra)}" if extra else ""),
                    off=kind in ("stay", "solo") and d in free,
                )
            )
            d += timedelta(days=1)
        rows.append((first.strftime("%b"), cells))
    return rows


def _block_view(b: Block) -> dict[str, object]:
    return {
        "dates": (
            f"{b.start:%a %d %b} – {b.end:%a %d %b %Y}"
            if b.start.year == b.end.year
            else f"{b.start:%a %d %b %Y} – {b.end:%a %d %b %Y}"
        ),
        "days": b.days,
        "paid": b.paid_days,
        "it": ", ".join(b.it_holidays),
        "peaks": ", ".join(b.peaks),
    }


def assumptions(c: Constraints, r: YearResult) -> list[str]:
    """What the plan takes as given, so Martin can correct it."""
    p = r.plan
    notes = [
        f"Stays in Faenza last {p.min_stay_nights} to {p.max_stay_nights} nights, with "
        f"{p.min_home_nights} to {p.max_home_nights} nights in Poznań between them. "
        "Holidays don't count as Poznań time. Of the rhythms that keep remote work "
        f"within {p.remote_share[0]:.0%} to {p.remote_share[1]:.0%} ({r.remote_share:.0%} "
        f"of {r.workdays} working days here), this one needs the fewest trips.",
        "Every stay starts and ends on a day off, so you can drive or fly without losing pay.",
        f"If La Suite is blocked during a stay, you stay alone elsewhere for at most "
        f"{c.solo_max_days} nights and Paula and Basia join when it is free.",
    ]
    for f in p.fixed_stays:
        notes.append(f"Fixed: {f.start:%d %b} to {f.end:%d %b}. {f.note}".strip())
    return notes


# Italian national holidays with a fixed date (Easter Monday moves; it comes from data).
IT_FIXED = {
    (1, 1): "New Year's Day",
    (1, 6): "Epiphany",
    (4, 25): "Liberation Day",
    (5, 1): "Labour Day",
    (6, 2): "Republic Day",
    (8, 15): "Ferragosto",
    (11, 1): "All Saints",
    (12, 8): "Immaculate Conception",
    (12, 25): "Christmas",
    (12, 26): "St Stephen",
}


def questions(c: Constraints, r: YearResult) -> list[str]:
    """Italian national holidays on a weekday that the Work calendar doesn't list."""
    it = {h.day for h in c.holidays if h.country == "IT"}
    out = []
    for (m, d), name in IT_FIXED.items():
        day = date(r.plan.year, m, d)
        shut = any(s.start <= day <= s.end for s in c.shutdown)
        if day.weekday() < 5 and day not in it and not shut:
            out.append(
                f"{name}, {day:%a %d %b}, is an Italian public holiday but isn't in your Work "
                "calendar. Is the office open that day? If it's closed, it makes a cheap "
                "long weekend."
            )
    return out


def render_year(c: Constraints, r: YearResult) -> str:
    year_days = [
        date(r.plan.year, 1, 1) + timedelta(days=i)
        for i in range((date(r.plan.year, 12, 31) - date(r.plan.year, 1, 1)).days + 1)
    ]
    free = free_days_off(c, r.plan.year)
    kinds = [_kind(c, r, d, free)[0] for d in year_days]
    totals = {
        "faenza": sum(st.nights for st in r.stays),
        "stays": len(r.stays),
        "holiday": sum(b.days for b in r.holidays),
        "paid": r.paid_days_off,
        "home": kinds.count("home"),
    }
    env = Environment(
        loader=PackageLoader("planner", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    return env.get_template("year.html.j2").render(
        r=r,
        c=c,
        months=_months(c, r),
        totals=totals,
        long=[(_block_view(b), b == r.long_pick) for b in r.long_options],
        second=[(_block_view(b), b == r.second_pick) for b in r.second_options],
        weekends=[_block_view(b) for b in r.weekends],
        winter=[_block_view(b) for b in r.winter],
        stays=r.stays,
        assumptions=assumptions(c, r),
        questions=questions(c, r),
    )


def _why(c: Constraints, r: YearResult, b: Block) -> str:
    """What makes a break: the planned holiday, a shutdown or an Italian holiday."""
    for h in r.holidays:
        if h.start <= b.start and b.end <= h.end or (b.start <= h.start and h.end <= b.end):
            if h == r.long_pick:
                return "Summer holiday (around the shutdown)"
            return "Two-week holiday"
    if any(s.start <= b.end and b.start <= s.end for s in c.shutdown):
        return "Christmas shutdown" if b.start.month in (12, 1) else "Shutdown"
    names = [
        h.name for h in c.holidays if h.country == "IT" and b.start <= h.day <= b.end and h.name
    ]
    if names:
        return "Long weekend: " + ", ".join(dict.fromkeys(names))
    if any(b.start <= d <= b.end for d in r.bridges):
        return "Long weekend (day off)"
    return "Days off"


def render_options(c: Constraints, results: list[YearResult]) -> str:
    """Several alternative years on one page, compared side by side."""
    from planner.year import with_bridges

    views = []
    for i, r in enumerate(results):
        cb = with_bridges(c, r.bridges)
        brks = []
        for b in r.breaks:
            v = _block_view(b)
            v["paid"] = sum(1 for d in r.bridges if b.start <= d <= b.end) + sum(
                h.paid_days for h in r.holidays if b.start <= h.start and h.end <= b.end
            )
            v["why"] = _why(c, r, b)
            brks.append(v)
        views.append(
            {
                "r": r,
                "anchor": f"option-{'abc'[i] if i < 3 else i}",
                "months": _months(cb, r),
                "breaks": brks,
                "faenza": sum(st.nights for st in r.stays),
            }
        )
    for key, attr, best in (
        ("best_off", "days_off_in_breaks", max),
        ("best_paid", "paid_days_off", min),
        ("best_trips", "trips", min),
    ):
        top = best(getattr(v["r"], attr) for v in views)
        for v in views:
            v[key] = len(views) > 1 and getattr(v["r"], attr) == top
    env = Environment(
        loader=PackageLoader("planner", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    year = results[0].plan.year
    return env.get_template("year_options.html.j2").render(
        options=views, year=year, peaks=results[0].plan.peaks
    )
