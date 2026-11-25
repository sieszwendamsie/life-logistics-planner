"""Draft plan of a whole year: holidays first, then stays in Faenza around them.

`planner year` answers two questions with the rules in docs/planning-rules.md:

1. Holidays. Which dates cost the fewest paid days? A holiday is a run of days
   off that starts right after a working day and ends right before one, so no
   free day next to it is left unused. Martin is paid per hour, so a holiday
   "costs" its working days only: weekends, Italian public holidays and
   shutdowns are free. Polish public holidays are normal working days for him.
   Ties are broken by school-holiday peaks (`year_plan.peaks`), when prices are
   higher.
2. Stays. With the holidays fixed, which Faenza stays fit the year? Stays start
   and end on days off (so Martin can drive), keep the Poznań gap between stays
   within the rules, cover every required office period, and avoid the family
   house's blocked dates (Martin may stay alone elsewhere for `solo_max_days`).

It is a draft rhythm, not a booking plan: no flight or price is checked here.
Each stay is planned later with `planner report` and the find-flights skill.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from planner.holidays import peak_days
from planner.models import AccommodationFile, Constraints, DateRange, YearPlan

DAY = timedelta(days=1)


def _days(a: date, b: date) -> list[date]:
    """Every day from a to b, both included."""
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def _overlaps(a: date, b: date, r: DateRange) -> bool:
    return a <= r.end and r.start <= b


# ------------------------------------------------------------------ holidays


@dataclass(frozen=True)
class Block:
    """A holiday: a run of days off, both ends included."""

    start: date
    end: date
    paid_days: int  # working days inside: the pay this holiday costs
    peak_score: int  # school-holiday peaks touched, summed per day
    peaks: tuple[str, ...]
    it_holidays: tuple[str, ...]

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def _peak_names(plan: YearPlan, d: date) -> list[str]:
    return [p.name for p in plan.peaks if p.start <= d <= p.end]


def _block(c: Constraints, plan: YearPlan, start: date, end: date) -> Block:
    days = _days(start, end)
    it = {h.day: h.name or "Italian holiday" for h in c.holidays if h.country == "IT"}
    names = sorted({n for d in days for n in _peak_names(plan, d)})
    return Block(
        start=start,
        end=end,
        paid_days=sum(not c.day_off(d) for d in days),
        peak_score=sum(len(_peak_names(plan, d)) for d in days),
        peaks=tuple(names),
        it_holidays=tuple(it[d] for d in days if d in it and d.weekday() < 5),
    )


def holiday_blocks(
    c: Constraints, plan: YearPlan, first: date, last: date, min_days: int, max_days: int
) -> list[Block]:
    """Every holiday between first and last whose length is within the limits."""
    # A holiday starts right after a working day and ends right before one, so it
    # never leaves a free day unused at either end.
    starts = [d for d in _days(first, last) if not c.day_off(d - DAY)]
    blocks = []
    for s in starts:
        for n in range(min_days, max_days + 1):
            e = s + timedelta(days=n - 1)
            if e > last:
                break
            if not c.day_off(e + DAY):
                blocks.append(_block(c, plan, s, e))
    return blocks


def _rank(b: Block) -> tuple:
    """Fewest paid days, then the most days off for them, then the fewest peaks."""
    return (b.paid_days, -b.days, b.peak_score, b.start)


def _summer_shutdown(c: Constraints, year: int) -> DateRange | None:
    for r in c.shutdown:
        if r.start.year == year and 6 <= r.start.month <= 9:
            return r
    return None


def _busy(c: Constraints, plan: YearPlan) -> list[DateRange]:
    """Dates no holiday may touch: office periods and decided stays."""
    return [*c.martin_italy(), *plan.fixed_stays]


def long_holidays(c: Constraints, plan: YearPlan, top: int = 4) -> list[Block]:
    """About four weeks around the summer shutdown, cheapest first."""
    shut = _summer_shutdown(c, plan.year)
    if shut is None:
        return []
    lo, hi = plan.long_holiday_days
    found = [
        b
        for b in holiday_blocks(
            c, plan, shut.start - timedelta(days=hi), shut.end + timedelta(days=hi), lo, hi
        )
        if b.start <= shut.start
        and shut.end <= b.end
        and not any(_overlaps(b.start, b.end, r) for r in _busy(c, plan))
    ]
    return sorted(found, key=_rank)[:top]


def second_holidays(
    c: Constraints, plan: YearPlan, long: Block | None, top: int = 4
) -> list[Block]:
    """Two weeks somewhere else in the year, apart from the long one, cheapest first."""
    lo, hi = plan.second_holiday_days
    first, last = max(plan.start, date(plan.year, 1, 1)), date(plan.year, 12, 31)
    away = timedelta(days=plan.holiday_gap_days)
    found = []
    for b in holiday_blocks(c, plan, first, last, lo, hi):
        if any(_overlaps(b.start, b.end, r) for r in [*_busy(c, plan), *c.shutdown]):
            continue
        if long and b.start < long.end + away and long.start - away < b.end:
            continue
        found.append(b)
    # One per month: the best block of each month is enough to choose from.
    best: dict[int, Block] = {}
    for b in sorted(found, key=_rank):
        best.setdefault(b.start.month, b)
    return sorted(best.values(), key=_rank)[:top]


def long_weekends(c: Constraints, plan: YearPlan, taken: list[Block]) -> list[Block]:
    """For each Italian holiday on a weekday: the cheapest long weekend (3 to 5 days)
    and, when one more paid day makes it longer, that one too."""
    result: list[Block] = []
    for h in sorted(c.holidays, key=lambda h: h.day):
        if h.country != "IT" or h.day.year != plan.year or h.day.weekday() >= 5:
            continue
        if any(b.start <= h.day <= b.end for b in taken) or any(
            r.start <= h.day <= r.end for r in c.shutdown
        ):
            continue
        around = holiday_blocks(c, plan, h.day - timedelta(days=4), h.day + timedelta(days=4), 3, 5)
        around = [b for b in around if b.start <= h.day <= b.end and b.paid_days <= 2]
        by_cost: dict[int, Block] = {}
        for b in sorted(around, key=lambda b: (b.paid_days, -b.days, b.start)):
            by_cost.setdefault(b.paid_days, b)
        options = sorted(by_cost.values(), key=lambda b: b.paid_days)
        # Keep only options that add days: paying more for the same length is pointless.
        kept: list[Block] = []
        for b in options:
            if not kept or b.days > kept[-1].days:
                kept.append(b)
        result.extend(kept)
    return result


def winter_extras(c: Constraints, plan: YearPlan) -> list[Block]:
    """Christmas shutdowns touching the year, made longer by at most
    `winter_extra_days` paid days (that period is busy at work)."""
    result: list[Block] = []
    for shut in c.shutdown:
        if shut.start.month != 12 or shut.start.year not in (plan.year - 1, plan.year):
            continue
        near = holiday_blocks(
            c,
            plan,
            shut.start - timedelta(days=7),
            shut.end + timedelta(days=7),
            (shut.end - shut.start).days + 1,
            (shut.end - shut.start).days + 15,
        )
        near = [
            b
            for b in near
            if b.start <= shut.start
            and shut.end <= b.end
            and 0 < b.paid_days <= plan.winter_extra_days
        ]
        # Per number of paid days, the longest break (earliest if equal).
        by_cost: dict[int, Block] = {}
        for b in sorted(near, key=_rank):
            by_cost.setdefault(b.paid_days, b)
        result.extend(sorted(by_cost.values(), key=_rank))
    return result


# --------------------------------------------------------------------- stays


@dataclass
class Stay:
    start: date  # travel day to Faenza (night of start is the first night)
    end: date  # travel day home
    fixed: bool = False
    note: str = ""
    blocked: list[date] = field(default_factory=list)  # La Suite not free these nights
    pl_holidays: list[str] = field(default_factory=list)
    peak_travel: list[str] = field(default_factory=list)
    school_peak_travel: list[str] = field(default_factory=list)
    office: list[DateRange] = field(default_factory=list)
    cost: float = 0.0

    @property
    def nights(self) -> int:
        return (self.end - self.start).days

    @property
    def blocked_nights(self) -> int:
        """Nights La Suite is not free: Martin alone elsewhere (or a city break)."""
        return len(self.blocked)

    @property
    def family_nights(self) -> int:
        return self.nights - self.blocked_nights


def _blocked(acc: AccommodationFile, start: date, end: date) -> list[date]:
    """Nights of the stay when the family house is not free."""
    house = next((a for a in acc.accommodation if a.preferred), None)
    if house is None:
        return []
    nights = [start + timedelta(days=i) for i in range((end - start).days)]
    if house.available:
        return [n for n in nights if not any(r.start <= n < r.end for r in house.available)]
    return [n for n in nights if any(r.start <= n < r.end for r in house.unavailable)]


def _evaluate(
    c: Constraints, acc: AccommodationFile, plan: YearPlan, s: date, e: date, fixed: bool
) -> Stay | None:
    stay = Stay(s, e, fixed=fixed)
    stay.blocked = _blocked(acc, s, e)
    if stay.blocked_nights > c.solo_max_days and not fixed:
        return None
    pl = {h.day: h.name or "Polish holiday" for h in c.holidays if h.country == "PL"}
    stay.pl_holidays = [f"{pl[d]} ({d:%d %b})" for d in _days(s, e) if d in pl]
    peaks = peak_days(c.holidays)
    for d in (s, e):
        if d in peaks:
            stay.peak_travel.append(f"{d:%a %d %b} ({peaks[d].country} long weekend)")
        names = _peak_names(plan, d)
        if names:
            stay.school_peak_travel.append(f"{d:%a %d %b} ({', '.join(names)})")
    stay.office = [o for o in c.martin_italy() if _overlaps(s, e, o)]
    target = (plan.min_stay_nights + plan.max_stay_nights) / 2
    stay.cost = (
        3 * stay.blocked_nights
        + 2 * len(stay.pl_holidays)
        + 2 * len(stay.peak_travel)
        + 1 * len(stay.school_peak_travel)
        + abs(stay.nights - target) / 7
    )
    return stay


def _candidates(
    c: Constraints, acc: AccommodationFile, plan: YearPlan, no_go: list[DateRange], last: date
) -> list[Stay]:
    found = []
    for s in _days(plan.start + DAY, last):
        if not c.day_off(s):
            continue
        for n in range(plan.min_stay_nights, plan.max_stay_nights + 1):
            e = s + timedelta(days=n)
            if e > last or not c.day_off(e):
                continue
            if any(_overlaps(s, e, r) for r in no_go):
                continue
            office = [o for o in c.martin_italy() if _overlaps(s, e, o)]
            # Office periods must lie fully inside, without travelling on them.
            if any(not (s < o.start and o.end < e) for o in office):
                continue
            stay = _evaluate(c, acc, plan, s, e, fixed=False)
            if stay:
                found.append(stay)
    return found


def _home_nights(a: date, b: date, holidays: list[Block]) -> int:
    """Nights in Poznań between coming back on a and leaving on b."""
    away = sum(max(0, (min(b, h.end + DAY) - max(a, h.start)).days) for h in holidays)
    return (b - a).days - away


def plan_stays(
    c: Constraints, acc: AccommodationFile, plan: YearPlan, holidays: list[Block]
) -> list[Stay]:
    """The cheapest chain of stays through the year (fewest compromises).

    A chain starts after `plan.start`, keeps every Poznań gap within
    `min_home_nights`..`max_home_nights` (holidays don't count as Poznań), includes
    every fixed stay and required office period, and ends with at most
    `max_home_nights` before the Christmas shutdown.
    """
    xmas = next(
        (r.start for r in c.shutdown if r.start.year == plan.year and r.start.month == 12),
        date(plan.year, 12, 31),
    )
    no_go = [
        *c.shutdown,
        *c.leave,
        *c.martin_away(),
        *c.other_travel,
        *(DateRange(start=h.start, end=h.end) for h in holidays),
    ]
    fixed = [
        st for f in plan.fixed_stays if (st := _evaluate(c, acc, plan, f.start, f.end, fixed=True))
    ]
    for st, f in zip(fixed, plan.fixed_stays, strict=True):
        st.note = f.note
    no_go_free = [*no_go, *plan.fixed_stays]
    nodes = sorted([*fixed, *_candidates(c, acc, plan, no_go_free, xmas)], key=lambda s: s.start)
    must = [*plan.fixed_stays, *c.martin_italy()]

    def between_ok(a: date, b: date) -> bool:
        # Nothing that must be in a stay may fall in the gap between a and b.
        return not any(a < m.start and m.end < b for m in must if m.start.year == plan.year)

    def gap_ok(a: date, b: date, relaxed: bool) -> bool:
        n = _home_nights(a, b, holidays)
        lo = 0 if relaxed else plan.min_home_nights
        return lo <= n <= plan.max_home_nights and between_ok(a, b)

    best: list[tuple[float, int]] = []  # (cost, previous index or -1)
    for i, st in enumerate(nodes):
        options: list[tuple[float, int]] = []
        if gap_ok(plan.start, st.start, relaxed=st.fixed):
            options.append((st.cost, -1))
        for j in range(i):
            prev = nodes[j]
            if prev.end > st.start or best[j][0] == float("inf"):
                continue
            if gap_ok(prev.end, st.start, relaxed=st.fixed or prev.fixed):
                gap = _home_nights(prev.end, st.start, holidays)
                target = (plan.min_home_nights + plan.max_home_nights) / 2
                options.append((best[j][0] + st.cost + abs(gap - target) / 7, j))
        best.append(min(options) if options else (float("inf"), -1))

    ends = [
        (best[i][0], i)
        for i, st in enumerate(nodes)
        if best[i][0] < float("inf")
        and _home_nights(st.end, xmas, holidays) <= plan.max_home_nights
        and between_ok(st.end, xmas)
    ]
    if not ends:
        return []
    _, i = min(ends)
    chain = []
    while i != -1:
        chain.append(nodes[i])
        i = best[i][1]
    return chain[::-1]


# ---------------------------------------------------------------------- plan


@dataclass
class YearResult:
    plan: YearPlan
    long_options: list[Block]
    second_options: list[Block]
    long_pick: Block | None
    second_pick: Block | None
    weekends: list[Block]
    winter: list[Block]
    stays: list[Stay]

    @property
    def holidays(self) -> list[Block]:
        return [b for b in (self.long_pick, self.second_pick) if b]

    @property
    def paid_days_off(self) -> int:
        return sum(b.paid_days for b in self.holidays)


def _pick(options: list[Block], start: date | None) -> Block | None:
    if start:
        return next((b for b in options if b.start == start), None)
    return options[0] if options else None


def build_year(c: Constraints, acc: AccommodationFile) -> YearResult:
    plan = c.year_plan
    if plan is None:
        raise ValueError("constraints have no year_plan section")
    long_options = long_holidays(c, plan)
    if plan.long_holiday_start and not _pick(long_options, plan.long_holiday_start):
        long_options = [
            *long_options,
            *[b for b in long_holidays(c, plan, top=50) if b.start == plan.long_holiday_start][:1],
        ]
    long_pick = _pick(long_options, plan.long_holiday_start)
    second_options = second_holidays(c, plan, long_pick, top=6)
    second_pick = _pick(second_options, plan.second_holiday_start)
    taken = [b for b in (long_pick, second_pick) if b]
    return YearResult(
        plan=plan,
        long_options=long_options,
        second_options=second_options,
        long_pick=long_pick,
        second_pick=second_pick,
        weekends=long_weekends(c, plan, taken),
        winter=winter_extras(c, plan),
        stays=plan_stays(c, acc, plan, taken),
    )


def text(c: Constraints, r: YearResult) -> str:
    """The plan as plain text for the terminal."""

    def blk(b: Block) -> str:
        extra = f"; Italian holiday: {', '.join(b.it_holidays)}" if b.it_holidays else ""
        peaks = f"; school holidays: {', '.join(b.peaks)}" if b.peaks else ""
        return (
            f"{b.start:%a %d %b} to {b.end:%a %d %b %Y}: {b.days} days off for "
            f"{b.paid_days} paid days{extra}{peaks}"
        )

    out = [f"Draft plan for {r.plan.year}", ""]
    out.append("Long holiday (around the summer shutdown), best first:")
    out += [("  * " if b == r.long_pick else "    ") + blk(b) for b in r.long_options]
    out.append("Two-week holiday, best first:")
    out += [("  * " if b == r.second_pick else "    ") + blk(b) for b in r.second_options]
    out.append("Long weekends around Italian holidays:")
    out += ["    " + blk(b) for b in r.weekends]
    out.append("Christmas shutdown, made longer:")
    out += ["    " + blk(b) for b in r.winter]
    out.append("")
    out.append(f"Stays in Faenza ({len(r.stays)}):")
    for st in r.stays:
        flags = []
        if st.fixed:
            flags.append(f"fixed: {st.note}" if st.note else "fixed")
        if st.blocked_nights:
            flags.append(f"La Suite blocked {st.blocked_nights} nights")
        if st.office:
            flags.append("office period inside")
        if st.pl_holidays:
            flags.append("Polish holiday: " + ", ".join(st.pl_holidays))
        if st.peak_travel:
            flags.append("travel on a long weekend: " + ", ".join(st.peak_travel))
        note = f"  ({'; '.join(flags)})" if flags else ""
        out.append(f"  {st.start:%a %d %b} to {st.end:%a %d %b}: {st.nights} nights{note}")
    if not r.stays:
        out.append("  No chain of stays fits. Loosen min/max_home_nights or the stay length.")
    return "\n".join(out)
