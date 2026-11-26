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
    """Dates no holiday may touch: office periods, decided stays and the periods
    Martin keeps free of longer holidays (`no_holiday`)."""
    return [*c.martin_italy(), *plan.fixed_stays, *plan.no_holiday]


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
    c: Constraints, plan: YearPlan, long: Block | None, top: int = 4, pinned: date | None = None
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
        if plan.second_holiday_months and b.start.month not in plan.second_holiday_months:
            continue
        found.append(b)
    if pinned:
        return [b for b in sorted(found, key=_rank) if b.start == pinned][:1]
    # One per half month: enough to choose from without near-duplicates.
    best: dict[tuple[int, bool], Block] = {}
    for b in sorted(found, key=_rank):
        best.setdefault((b.start.month, b.start.day > 15), b)
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
    # Family events Martin would rather be in Poland for (#PL #pref).
    pl_wishes: list[str] = field(default_factory=list)
    peak_travel: list[str] = field(default_factory=list)
    school_peak_travel: list[str] = field(default_factory=list)
    office: list[DateRange] = field(default_factory=list)
    # Bridge-day long weekends spent in Faenza at the start or end of the stay.
    long_weekends: list[str] = field(default_factory=list)
    joined: bool = False  # the one-week holiday starts or ends where this stay does
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
    wishes = [
        p for p in c.presence if "Martin" in p.who and p.where == "PL" and p.strength == "pref"
    ]
    stay.pl_wishes = [
        f"{p.title or 'event'} ({p.start:%d %b})" for p in wishes if _overlaps(s, e, p)
    ]
    peaks = peak_days(c.holidays)
    for d in (s, e):
        if d in peaks:
            stay.peak_travel.append(f"{d:%a %d %b} ({peaks[d].country} long weekend)")
        names = _peak_names(plan, d)
        if names:
            stay.school_peak_travel.append(f"{d:%a %d %b} ({', '.join(names)})")
    stay.office = [o for o in c.martin_italy() if _overlaps(s, e, o)]
    # With a trip limit, longer stays are better (fewer trips, more office days).
    target = (
        plan.max_stay_nights
        if plan.max_trips
        else (plan.min_stay_nights + plan.max_stay_nights) / 2
    )
    stay.cost = (
        # Martin: avoid La Suite blocked nights in Faenza (weighs more than a
        # week's difference in length or a missed wish).
        25 * stay.blocked_nights
        + 2 * len(stay.pl_holidays)
        + 15 * len(stay.pl_wishes)
        + 2 * len(stay.peak_travel)
        + 1 * len(stay.school_peak_travel)
        + abs(stay.nights - target) / 7
    )
    if plan.max_trips:
        # Few trips leave few office days: each working day in Faenza is a plus.
        stay.cost -= 0.5 * sum(1 for d in _days(s + DAY, e - DAY) if not c.day_off(d))
    return stay


def _edge_only(c: Constraints, s: date, e: date, bridges: frozenset[date]) -> bool:
    """True if every bridge day inside s..e belongs to the run of days off that the
    stay starts or ends in: the long weekend is spent in Faenza next to travel."""
    for d in _days(s, e):
        if d not in bridges:
            continue
        if not (all(c.day_off(x) for x in _days(s, d)) or all(c.day_off(x) for x in _days(d, e))):
            return False
    return True


def _trip_long_weekends(c: Constraints, s: date, e: date, bridges: frozenset[date]) -> list[str]:
    inside = [d for d in _days(s, e) if d in bridges]
    out = []
    for d in inside:
        run_start = d
        while c.day_off(run_start - DAY):
            run_start -= DAY
        run_end = d
        while c.day_off(run_end + DAY):
            run_end += DAY
        label = f"{run_start:%d %b}-{run_end:%d %b}"
        if label not in out:
            out.append(label)
    return out


def _candidates(
    c: Constraints,
    acc: AccommodationFile,
    plan: YearPlan,
    no_go: list[DateRange],
    last: date,
    bridges: frozenset[date] = frozenset(),
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
            if bridges and not plan.long_weekends_anywhere and not _edge_only(c, s, e, bridges):
                continue
            office = [o for o in c.martin_italy() if _overlaps(s, e, o)]
            # Office periods must lie fully inside, without travelling on them.
            if any(not (s < o.start and o.end < e) for o in office):
                continue
            stay = _evaluate(c, acc, plan, s, e, fixed=False)
            if stay:
                stay.long_weekends = _trip_long_weekends(c, s, e, bridges)
                # A long weekend in Faenza next to travel is a small plus.
                stay.cost -= 2 * len(stay.long_weekends)
                found.append(stay)
    return found


def _home_nights(a: date, b: date, holidays: list[Block]) -> int:
    """Nights in Poznań between coming back on a and leaving on b."""
    away = sum(max(0, (min(b, h.end + DAY) - max(a, h.start)).days) for h in holidays)
    return (b - a).days - away


def plan_stays(
    c: Constraints,
    acc: AccommodationFile,
    plan: YearPlan,
    holidays: list[Block],
    bridges: frozenset[date] = frozenset(),
    not_home: list[Block] | None = None,
    joined: Block | None = None,
) -> list[Stay]:
    """The cheapest chain of stays through the year (fewest compromises).

    A chain starts after `plan.start`, keeps every Poznań gap within
    `min_home_nights`..`max_home_nights` (holidays don't count as Poznań), includes
    every fixed stay and required office period, and ends with at most
    `max_home_nights` before the Christmas shutdown. Bridge days may fall inside
    a stay only next to its travel days (a long weekend spent in Faenza).
    """
    xmas = next(
        (r.start for r in c.shutdown if r.start.year == plan.year and r.start.month == 12),
        date(plan.year, 12, 31),
    )
    # `not_home`: holidays that don't count as Poznań time in a gap (default: all).
    # `joined`: a holiday that should start where a stay ends, or end where one
    # starts (travel on from Faenza), so a stay may touch it.
    gap_holidays = holidays if not_home is None else not_home
    no_go = [
        *c.shutdown,
        *c.leave,
        *c.martin_away(),
        *c.other_travel,
        *(
            DateRange(start=h.start + DAY, end=h.end - DAY)
            if h is joined
            else DateRange(start=h.start, end=h.end)
            for h in holidays
        ),
    ]
    no_go = [r for r in no_go if not (r.start == r.end and r.start in bridges)]
    fixed = [
        st for f in plan.fixed_stays if (st := _evaluate(c, acc, plan, f.start, f.end, fixed=True))
    ]
    for st, f in zip(fixed, plan.fixed_stays, strict=True):
        st.note = f.note
    no_go_free = [*no_go, *plan.fixed_stays]
    nodes = sorted(
        [*fixed, *_candidates(c, acc, plan, no_go_free, xmas, bridges)], key=lambda s: s.start
    )
    if joined:
        for st in nodes:
            if not st.fixed and (st.end == joined.start or st.start == joined.end):
                st.joined = True
                st.cost -= 200  # strongly prefer a chain that travels on to the holiday
    must = [*plan.fixed_stays, *c.martin_italy()]

    def between_ok(a: date, b: date) -> bool:
        # Nothing that must be in a stay may fall in the gap between a and b.
        return not any(a < m.start and m.end < b for m in must if m.start.year == plan.year)

    def gap_ok(a: date, b: date, relaxed: bool) -> bool:
        n = _home_nights(a, b, gap_holidays)
        lo = 0 if relaxed else plan.min_home_nights
        return lo <= n <= plan.max_home_nights and between_ok(a, b)

    # best[i][(k, n)]: cheapest chain ending with stay i that joins k long weekends
    # to stays (at most plan.trip_long_weekends) and has n stays (at most
    # plan.max_trips), as (cost, previous i, previous key).
    cap = plan.trip_long_weekends
    most = plan.max_trips or len(nodes) + 1
    inf = float("inf")
    # The aimed-for gap ignores any stretch of the longest time away.
    target = sum(plan.away_nights or (plan.min_home_nights, plan.max_home_nights)) / 2
    Key = tuple[int, int]
    best: list[dict[Key, tuple[float, int, Key]]] = []
    for st in nodes:
        here: dict[Key, tuple[float, int, Key]] = {}
        own = len(st.long_weekends)

        def offer(key: Key, cost: float, j: int, pk: Key, here: dict = here) -> None:
            if key[0] <= cap and key[1] <= most and cost < here.get(key, (inf, -1, (0, 0)))[0]:
                here[key] = (cost, j, pk)

        if gap_ok(plan.start, st.start, relaxed=st.fixed):
            offer((own, 1), st.cost, -1, (-1, -1))
        for j, prev in enumerate(nodes[: len(best)]):
            if prev.end > st.start or not best[j]:
                continue
            if gap_ok(prev.end, st.start, relaxed=st.fixed or prev.fixed):
                gap = _home_nights(prev.end, st.start, gap_holidays)
                step = st.cost + abs(gap - target) / 7
                for (k, n), (cost, _, _) in best[j].items():
                    offer((k + own, n + 1), cost + step, j, (k, n))
        best.append(here)

    ends = [
        (cost, i, key)
        for i, st in enumerate(nodes)
        if _home_nights(st.end, xmas, gap_holidays) <= plan.max_home_nights
        and between_ok(st.end, xmas)
        for key, (cost, _, _) in best[i].items()
    ]
    if not ends:
        return []
    _, i, key = min(ends)
    chain = []
    while i != -1:
        chain.append(nodes[i])
        _, i, key = best[i][key]
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
    workdays: int = 0  # working days in the year, holidays taken out
    office_days: int = 0  # working days inside Faenza stays
    label: str = ""
    note: str = ""
    bridges: list[date] = field(default_factory=list)  # paid days for long weekends
    breaks: list[Block] = field(default_factory=list)  # every run of 3+ days off
    suite_blocked: list[date] = field(default_factory=list)  # nights La Suite is not free
    other_travel: list[DateRange] = field(default_factory=list)  # e.g. UK visits

    @property
    def holidays(self) -> list[Block]:
        return [b for b in (self.long_pick, self.second_pick) if b]

    @property
    def remote_share(self) -> float:
        return 1 - self.office_days / self.workdays if self.workdays else 1.0

    @property
    def paid_days_off(self) -> int:
        return sum(b.paid_days for b in self.holidays) + len(self.bridges)

    @property
    def days_off_in_breaks(self) -> int:
        """Days of the year in breaks of 3 days or more (holidays, long weekends,
        shutdowns); a Christmas break is counted only for its days in this year."""
        y = self.plan.year
        return sum(
            (min(b.end, date(y, 12, 31)) - max(b.start, date(y, 1, 1))).days + 1
            for b in self.breaks
        )

    @property
    def trips(self) -> int:
        """Round trips to Faenza (each is two travel days)."""
        return len(self.stays)


def _pick(options: list[Block], start: date | None) -> Block | None:
    if start:
        return next((b for b in options if b.start == start), None)
    return options[0] if options else None


def work_split(
    c: Constraints, year: int, stays: list[Stay], holidays: list[Block]
) -> tuple[int, int]:
    """(working days in the year, of which in Faenza). Travel days are days off."""
    first, last = date(year, 1, 1), date(year, 12, 31)
    work = [
        d
        for d in _days(first, last)
        if not c.day_off(d) and not any(b.start <= d <= b.end for b in holidays)
    ]
    office = [d for d in work if any(st.start < d < st.end for st in stays)]
    return len(work), len(office)


# Stay and gap lengths (nights) to try when the configured rhythm misses the
# remote-work share. The configured one is always tried first.
RHYTHMS = [
    (21, 35, 14, 35),
    (28, 35, 14, 42),
    (21, 35, 21, 35),
    (21, 35, 14, 28),
    (28, 35, 14, 28),
    (21, 28, 28, 42),
    (21, 28, 35, 49),
    (21, 35, 35, 56),
    (21, 35, 42, 63),
    (18, 28, 28, 42),
    (14, 28, 28, 42),
    (14, 21, 21, 35),
    (14, 21, 14, 28),
]


def _best_rhythm(
    c: Constraints,
    acc: AccommodationFile,
    plan: YearPlan,
    taken: list[Block],
    bridges: frozenset[date],
    not_home: list[Block] | None,
    joined: Block | None,
    lo: float,
    hi: float,
    mid: float,
    extra: int = 0,
) -> tuple[tuple, YearPlan, list[Stay], int, int] | None:
    tries = [plan] + [
        plan.model_copy(
            update={
                "min_stay_nights": a,
                "max_stay_nights": b,
                "min_home_nights": plan.away_nights[0] if plan.away_nights else g,
                "max_home_nights": (plan.away_nights[1] if plan.away_nights else h) + extra,
            }
        )
        for a, b, g, h in RHYTHMS
        # Stays never longer than the general stay rule (Martin: keep stay lengths).
        if c.stay_rules is None or b <= c.stay_rules.max_stay_days
    ]
    best: tuple[tuple, YearPlan, list[Stay], int, int] | None = None
    for i, p in enumerate(tries):
        stays = plan_stays(c, acc, p, taken, bridges, not_home, joined)
        if not stays:
            continue
        work, office = work_split(c, plan.year, stays, taken)
        share = 1 - office / work if work else 1.0
        miss = 0.0 if lo <= share <= hi else min(abs(share - lo), abs(share - hi))
        # Fewest La Suite blocked nights first (Martin, 26 Nov: priority), then
        # the remote share in range, fewest trips, fewest family events missed
        # (#pref Poland), the share closest to the middle; the configured rhythm
        # wins ties.
        wishes = sum(len(st.pl_wishes) for st in stays)
        blocked = sum(st.blocked_nights for st in stays if not st.fixed)
        score = (blocked, miss, len(stays), wishes, abs(share - mid), i)
        if best is None or score < best[0]:
            best = (score, p, stays, work, office)
    return best


def _plan_with_share(
    c: Constraints,
    acc: AccommodationFile,
    plan: YearPlan,
    taken: list[Block],
    bridges: frozenset[date] = frozenset(),
    not_home: list[Block] | None = None,
    joined: Block | None = None,
) -> tuple[YearPlan, list[Stay], int, int]:
    """The rhythm (configured or tried) with the remote share in range and the
    fewest trips; if none is in range, the one closest to it."""
    lo, hi = plan.remote_share
    mid = (lo + hi) / 2
    # With a trip limit, stretch the longest time away a week at a time until a
    # plan fits (Martin: fewer trips first).
    stretch = [0, 7, 14, 21, 28, 35, 42] if plan.max_trips and plan.away_nights else [0]
    best: tuple[tuple, YearPlan, list[Stay], int, int] | None = None
    for extra in stretch:
        base = plan
        if extra:
            base = plan.model_copy(update={"max_home_nights": plan.max_home_nights + extra})
        found = _best_rhythm(c, acc, base, taken, bridges, not_home, joined, lo, hi, mid, extra)
        if found is not None and (best is None or found[0][:2] < best[0][:2]):
            best = found
        if best is not None and best[0][1] == 0:
            break
    if best is None:
        return plan, [], 0, 0
    return best[1], best[2], best[3], best[4]


def breaks(c: Constraints, year: int, holidays: list[Block], min_days: int = 3) -> list[Block]:
    """Every run of at least `min_days` days off that touches the year (weekends,
    holidays, shutdowns, leave and bridge days), with its full dates."""
    plan = c.year_plan
    assert plan is not None
    first, last = date(year, 1, 1) - timedelta(days=21), date(year, 12, 31) + timedelta(days=21)

    def off(d: date) -> bool:
        return c.day_off(d) or any(b.start <= d <= b.end for b in holidays)

    out, d = [], first
    while d <= last:
        if not off(d):
            d += DAY
            continue
        start = d
        while d <= last and off(d):
            d += DAY
        end = d - DAY
        if (d - start).days >= min_days and start.year <= year <= end.year:
            out.append(_block(c, plan, start, end))
    return out


def with_bridges(c: Constraints, days: list[date]) -> Constraints:
    """The constraints with bridge days taken as leave (days off that cost pay)."""
    if not days:
        return c
    extra = [DateRange(start=d, end=d) for d in days]
    return c.model_copy(update={"leave": [*c.leave, *extra]})


def build_options(c: Constraints, acc: AccommodationFile) -> list[YearResult]:
    """One result per `year_plan.options` entry (or the single plan if none)."""
    plan = c.year_plan
    if plan is None:
        raise ValueError("constraints have no year_plan section")
    if not plan.options:
        return [build_year(c, acc)]
    results = []
    for opt in plan.options:
        changed = plan.model_copy(
            update={
                "long_holiday_start": opt.long_holiday_start or plan.long_holiday_start,
                "second_holiday_start": opt.second_holiday_start or plan.second_holiday_start,
                "second_holiday_days": opt.second_holiday_days or plan.second_holiday_days,
                "trip_long_weekends": (
                    plan.trip_long_weekends
                    if opt.trip_long_weekends is None
                    else opt.trip_long_weekends
                ),
                "long_weekends_anywhere": (
                    plan.long_weekends_anywhere
                    if opt.long_weekends_anywhere is None
                    else opt.long_weekends_anywhere
                ),
                "options": [],
            }
        )
        co = c.model_copy(
            update={"year_plan": changed, "other_travel": [*c.other_travel, *opt.other_travel]}
        )
        r = build_year(co, acc, opt.bridge_days)
        r.label, r.note = opt.label, opt.note
        results.append(r)
    return results


def build_year(
    c: Constraints, acc: AccommodationFile, bridge_days: list[date] | None = None
) -> YearResult:
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
    start = plan.second_holiday_start
    if start and not _pick(second_options, start):
        second_options = [*second_holidays(c, plan, long_pick, pinned=start), *second_options]
    second_pick = _pick(second_options, start)
    taken = [b for b in (long_pick, second_pick) if b]
    # Bridge days are leave (not worked). A stay may hold them only next to its
    # travel days, so the long weekend is spent in Faenza.
    bridges = sorted(
        d
        for d in (bridge_days or [])
        if not c.day_off(d) and not any(b.start <= d <= b.end for b in taken)
    )
    cb = with_bridges(c, bridges)
    # With `away_nights`, the time between stays counts every night away from the
    # Faenza office, holidays included, except the long summer holiday.
    not_home = [long_pick] if plan.away_nights and long_pick else None
    joined = second_pick if plan.second_holiday_joined else None
    rhythm, stays, work, office = _plan_with_share(
        cb, acc, plan, taken, frozenset(bridges), not_home, joined
    )
    return YearResult(
        plan=rhythm,
        long_options=long_options,
        second_options=second_options,
        long_pick=long_pick,
        second_pick=second_pick,
        weekends=long_weekends(c, plan, taken),
        winter=winter_extras(c, plan),
        stays=stays,
        workdays=work,
        office_days=office,
        bridges=bridges,
        breaks=breaks(cb, plan.year, taken),
        suite_blocked=_blocked(acc, date(plan.year, 1, 1), date(plan.year + 1, 1, 1)),
        other_travel=list(c.other_travel),
    )


def check_year(c: Constraints, r: YearResult) -> list[str]:
    """Problems where the plan breaks one of Martin's yearly rules (empty if none)."""
    plan, out = r.plan, []
    shut = _summer_shutdown(c, plan.year)
    lo_d, hi_d = plan.long_holiday_days
    if r.long_pick is None:
        out.append("No long holiday found around the summer shutdown.")
    else:
        b = r.long_pick
        if not lo_d <= b.days <= hi_d:
            out.append(f"Long holiday is {b.days} days, rule is {lo_d}-{hi_d}.")
        if shut and not (b.start <= shut.start and shut.end <= b.end):
            out.append("Long holiday does not cover the summer shutdown.")
    lo_d, hi_d = plan.second_holiday_days
    if r.second_pick is None:
        out.append("No second (two-week) holiday found.")
    else:
        b = r.second_pick
        if not lo_d <= b.days <= hi_d:
            out.append(f"Second holiday is {b.days} days, rule is {lo_d}-{hi_d}.")
        if plan.second_holiday_months and b.start.month not in plan.second_holiday_months:
            months = ", ".join(str(m) for m in plan.second_holiday_months)
            out.append(f"Second holiday starts in month {b.start.month}, rule is month {months}.")
    for b in r.winter:
        if b.paid_days > plan.winter_extra_days:
            out.append(
                f"Winter shutdown extended by {b.paid_days} paid days, max is "
                f"{plan.winter_extra_days}."
            )
    lo, hi = plan.remote_share
    if r.stays and not lo <= round(r.remote_share, 2) <= hi:
        out.append(f"Remote share is {r.remote_share:.0%}, target {lo:.0%}-{hi:.0%}.")
    for b in r.holidays:
        for q in plan.no_holiday:
            if b.start <= q.end and q.start <= b.end:
                out.append(
                    f"Holiday {b.start:%d %b}-{b.end:%d %b} falls in a no-holiday period "
                    f"({q.start:%d %b}-{q.end:%d %b})."
                )
    joined_ok = r.second_pick if plan.second_holiday_joined else None
    for st in r.stays:
        for b in r.holidays:
            touch = b is joined_ok and (st.end == b.start or st.start == b.end)
            if st.start <= b.end and b.start <= st.end and not touch:
                out.append(f"Stay {st.start:%d %b}-{st.end:%d %b} overlaps a holiday.")
    if plan.second_holiday_joined and r.second_pick and not any(st.joined for st in r.stays):
        out.append("The one-week holiday is not joined to a Faenza stay.")
    if plan.away_nights and r.stays:
        lo_a, hi_a = plan.away_nights
        free = [r.long_pick] if r.long_pick else []
        for a, b in zip(r.stays, r.stays[1:], strict=False):
            n = _home_nights(a.end, b.start, free)
            if n > hi_a:
                out.append(
                    f"{n} nights away from the office between {a.end:%d %b} and "
                    f"{b.start:%d %b}, max is {hi_a}"
                    + (" (stretched to keep the trip limit)." if plan.max_trips else ".")
                )
    if plan.max_trips and r.trips > plan.max_trips:
        out.append(f"{r.trips} Faenza trips, max is {plan.max_trips}.")
    joined = sum(len(st.long_weekends) for st in r.stays)
    if joined > plan.trip_long_weekends:
        out.append(
            f"{joined} long weekends are joined to Faenza stays, max is {plan.trip_long_weekends}."
        )
    return out


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
    out.append(
        f"Remote work: {r.remote_share:.0%} of {r.workdays} working days "
        f"(target {r.plan.remote_share[0]:.0%} to {r.plan.remote_share[1]:.0%}); "
        f"stays {r.plan.min_stay_nights}-{r.plan.max_stay_nights} nights, "
        f"{r.plan.min_home_nights}-{r.plan.max_home_nights} nights home between"
    )
    out.append(f"Stays in Faenza ({len(r.stays)}):")
    for st in r.stays:
        flags = []
        if st.fixed:
            flags.append(f"fixed: {st.note}" if st.note else "fixed")
        if st.blocked_nights:
            flags.append(f"La Suite blocked {st.blocked_nights} nights")
        if st.office:
            flags.append("office period inside")
        if st.long_weekends:
            flags.append("long weekend in Faenza: " + ", ".join(st.long_weekends))
        if st.joined:
            flags.append("joined to the one-week holiday")
        if st.pl_holidays:
            flags.append("Polish holiday: " + ", ".join(st.pl_holidays))
        if st.pl_wishes:
            flags.append("you'd rather be in Poland: " + ", ".join(st.pl_wishes))
        if st.peak_travel:
            flags.append("travel on a long weekend: " + ", ".join(st.peak_travel))
        note = f"  ({'; '.join(flags)})" if flags else ""
        out.append(f"  {st.start:%a %d %b} to {st.end:%a %d %b}: {st.nights} nights{note}")
    if not r.stays:
        out.append("  No chain of stays fits. Loosen min/max_home_nights or the stay length.")
    problems = check_year(c, r)
    out.append("")
    out.append("Rule check: " + ("all yearly rules met." if not problems else ""))
    out += [f"  ! {p}" for p in problems]
    return "\n".join(out)
