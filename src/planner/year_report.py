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


def _kind(c: Constraints, r: YearResult, d: date) -> tuple[str, str]:
    for st in r.stays:
        if st.start <= d <= st.end:
            label = f"Faenza {st.start:%d %b} to {st.end:%d %b}"
            if d in (st.start, st.end):
                label += " (travel day)"
            return ("solo" if _blocked(st, d) else "stay"), label
    for b in r.holidays:
        if b.start <= d <= b.end:
            return "holiday", f"Holiday {b.start:%d %b} to {b.end:%d %b}"
    if any(s.start <= d <= s.end for s in c.shutdown):
        return "shutdown", "Shutdown (office closed)"
    return "home", "Poznań"


def _blocked(st: Stay, d: date) -> bool:
    return d in st.blocked


def _months(c: Constraints, r: YearResult) -> list[tuple[str, list[Cell]]]:
    it = {h.day: h.name for h in c.holidays if h.country == "IT"}
    pl = {h.day: h.name for h in c.holidays if h.country == "PL"}
    rows = []
    for m in range(1, 13):
        first = date(r.plan.year, m, 1)
        cells = []
        d = first
        while d.month == m:
            kind, title = _kind(c, r, d)
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
        f"{p.min_home_nights} to {p.max_home_nights} nights in Poznań between them "
        "(your 2026 pattern). Holidays don't count as Poznań time.",
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
    kinds = [_kind(c, r, d)[0] for d in year_days]
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
