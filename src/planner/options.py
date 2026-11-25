"""Turn date windows into full options: where to stay, who travels how and when.

Rules (see docs/spec.md, steps 3 and 5):
- The family house (the preferred accommodation) must be free for most of the stay.
  Without it, the family does not travel and the window is dropped.
- If the house is free for only part of the window, Martin stays alone in another
  place before the family arrives and/or after it leaves, for at most
  `solo_max_days` nights in total.
- Flights: direct only (if `travel.direct_only`), on the routes in
  `travel.route_tiers`, best tier first. A leg with no such flight is kept as a con
  ("ask for an alternative route") so it can be researched.
- Car: for long enough stays with no other travel nearby, Martin drives and the
  family flies. This is preferred when allowed.
- 3-way trips: with `onward` set, the stay ends with everyone flying on to a
  third country and home from there; the car is not used.
- Ranking is about timing first, cost last.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

from planner.holidays import LongWeekend, peak_days
from planner.models import (
    Accommodation,
    AccommodationFile,
    Constraints,
    OnwardTrip,
    OptionsFile,
    TransportOption,
    Travel,
)
from planner.windows import Window

Who = Literal["everyone", "Martin", "family"]
Direction = Literal["outbound", "return", "onward", "home"]
Mode = Literal["flight", "car"]


@dataclass
class Leg:
    who: Who
    direction: Direction
    day: date
    mode: Mode = "flight"
    choice: TransportOption | None = None
    tier: int | None = None  # 1 = best route group
    hours: float | None = None  # door to door

    @property
    def missing(self) -> bool:
        return self.mode == "flight" and self.choice is None


@dataclass
class Option:
    window: Window
    house: Accommodation
    house_start: date
    house_end: date
    solo_place: Accommodation | None
    solo_nights: int
    martin_drives: bool
    legs: list[Leg]
    total_cost_eur: float
    martin_hours: float  # Martin's door-to-door travel time, both ways
    family_hours: float  # Paula and Basia's door-to-door travel time, both ways
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    # Days Paula and Basia are in Italy (first night, day they fly back).
    family_start: date | None = None
    family_end: date | None = None
    # How many soft preferences the option breaks (weekday or off-hours family
    # flights, long-weekend flights, holidays spent in Italy). Ranked after timing.
    soft: int = 0

    @property
    def family_together(self) -> bool:
        """The whole family stays at the house for the whole stay."""
        return self.solo_nights == 0

    @property
    def missing_legs(self) -> list[Leg]:
        return [leg for leg in self.legs if leg.missing]

    @property
    def travel_hours(self) -> float:
        """The longer of Martin's and the family's travel time."""
        return max(self.martin_hours, self.family_hours)

    @property
    def worst_tier(self) -> int:
        return max((leg.tier for leg in self.legs if leg.tier is not None), default=0)


def _free_ranges(place: Accommodation, lo: date, hi: date) -> list[tuple[date, date]]:
    """Free night ranges [s, e) of a place, clipped to [lo, hi)."""
    base = [(r.start, r.end) for r in place.available] or [(lo, hi)]
    ranges = [(max(s, lo), min(e, hi)) for s, e in base]
    return _subtract(ranges, [(b.start, b.end) for b in place.unavailable])


def _subtract(
    ranges: list[tuple[date, date]], blocks: list[tuple[date, date]]
) -> list[tuple[date, date]]:
    """Remove half-open block ranges from half-open ranges."""
    for b_start, b_end in blocks:
        cut: list[tuple[date, date]] = []
        for s, e in ranges:
            if b_end <= s or e <= b_start:
                cut.append((s, e))
                continue
            if s < b_start:
                cut.append((s, b_start))
            if b_end < e:
                cut.append((b_end, e))
        ranges = cut
    return [(s, e) for s, e in ranges if s < e]


def _free(place: Accommodation, start: date, end: date) -> bool:
    """True if the place is free for the nights start .. end-1."""
    return any(s <= start and end <= e for s, e in _free_ranges(place, start, end))


def _tier(travel: Travel, o: TransportOption, onward: OnwardTrip | None) -> int | None:
    """Route choice for a flight (1 = best), or None if it is not on Martin's routes.

    For the onward and home legs of a 3-way trip, the third-country airport must be
    one of `onward.airports`, and the Italian or Polish end is ranked like the
    normal routes.
    """
    tiers = travel.route_tiers
    if o.direction in ("onward", "home"):
        if onward is None:
            return None
        third, mine = (
            (o.destination, o.origin) if o.direction == "onward" else (o.origin, o.destination)
        )
        if third not in onward.airports:
            return None
        if not tiers:
            return 1
        for i, t in enumerate(tiers, start=1):
            side = t.destinations if o.direction == "onward" else t.origins
            if mine in side:
                return i
        return None
    if not tiers:
        return 1
    home, away = (
        (o.origin, o.destination)
        if o.direction == "outbound"
        else (
            o.destination,
            o.origin,
        )
    )
    for i, t in enumerate(tiers, start=1):
        if home in t.origins and away in t.destinations:
            return i
    return None


def _door_hours(travel: Travel, o: TransportOption) -> float:
    flight = (o.arrive - o.depart).total_seconds() / 3600
    th = travel.transfer_hours
    return flight + th.get(o.origin, 0) + th.get(o.destination, 0)


def _flight(
    transport: OptionsFile,
    travel: Travel,
    who: Who,
    d: Direction,
    day: date,
    onward: OnwardTrip | None = None,
) -> Leg:
    best: tuple[tuple[int, float, float], TransportOption, int, float] | None = None
    for o in transport.options:
        if o.direction != d or o.depart.date() != day:
            continue
        if travel.direct_only and o.stops:
            continue
        tier = _tier(travel, o, onward)
        if tier is None:
            continue
        hours = _door_hours(travel, o)
        key = (tier, hours, o.price_eur)
        if best is None or key < best[0]:
            best = (key, o, tier, hours)
    if best is None:
        return Leg(who, d, day)
    _, o, tier, hours = best
    return Leg(who, d, day, "flight", o, tier, round(hours, 2))


def _family_flight(
    transport: OptionsFile, travel: Travel, d: Direction, day: date, lo: date, hi: date
) -> Leg:
    """Paula and Basia's flight: the best day between lo and hi (both included).

    Weekend first, then a departure inside the preferred hours, then route
    choice, then the fewest days moved, door-to-door time and price.
    If no day has a flight, the leg stays open on the best day to search.
    """
    prefs = travel.family_flights
    candidates = [lo + timedelta(days=i) for i in range((hi - lo).days + 1)] or [day]
    best: tuple[tuple, Leg] | None = None
    for cand in candidates:
        leg = _flight(transport, travel, "family", d, cand)
        weekday = prefs.weekend and cand.weekday() < 5
        off_hours = leg.choice is not None and not (
            prefs.earliest <= leg.choice.depart.time() <= prefs.latest
        )
        key = (
            leg.missing,
            weekday,
            off_hours,
            leg.tier or 0,
            abs((cand - day).days),
            leg.hours or 0,
            leg.choice.price_eur if leg.choice else 0,
        )
        if best is None or key < best[0]:
            best = (key, leg)
    assert best is not None
    return best[1]


def _car_allowed(c: Constraints, w: Window) -> bool:
    car = c.travel.car
    if car is None or c.onward is not None or w.days < car.min_stay_days:
        return False
    if car.days_off_only and not (c.day_off(w.start) and c.day_off(w.end)):
        return False
    lo, hi = w.start - timedelta(days=car.clear_days), w.end + timedelta(days=car.clear_days)
    return not any(t.start <= hi and lo <= t.end for t in c.other_travel)


def _price(place: Accommodation) -> float:
    return place.price_per_night_eur if place.price_per_night_eur is not None else float("inf")


def _legs(
    c: Constraints, transport: OptionsFile, w: Window, hs: date, he: date, drive: bool
) -> list[Leg]:
    travel = c.travel
    shift = timedelta(days=travel.family_flights.shift_days)
    last_out = max(hs, min(hs + shift, he - timedelta(days=1)))
    first_back = min(he, max(he - shift, hs + timedelta(days=1)))

    def family_out() -> Leg:
        return _family_flight(transport, travel, "outbound", hs, hs, last_out)

    def family_back() -> Leg:
        return _family_flight(transport, travel, "return", he, first_back, he)

    if drive:
        hours = travel.car.drive_hours if travel.car else None
        return [
            Leg("Martin", "outbound", w.start, "car", hours=hours),
            family_out(),
            family_back(),
            Leg("Martin", "return", w.end, "car", hours=hours),
        ]
    plan: list[tuple[Who, Direction, date]]
    if hs > w.start:
        plan = [("Martin", "outbound", w.start), ("family", "outbound", hs)]
    else:
        plan = [("everyone", "outbound", w.start)]
    if c.onward is not None:
        home_day = w.end + timedelta(days=c.onward.nights)
        plan += [("everyone", "onward", w.end), ("everyone", "home", home_day)]
    elif he < w.end:
        plan += [("family", "return", he), ("Martin", "return", w.end)]
    else:
        plan += [("everyone", "return", w.end)]
    legs = []
    for who, d, day in plan:
        if who == "family":
            legs.append(family_out() if d == "outbound" else family_back())
        else:
            legs.append(_flight(transport, travel, who, d, day, c.onward))
    return legs


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days)]


def _soft_cons(
    c: Constraints,
    legs: list[Leg],
    w: Window,
    fam_start: date,
    fam_end: date,
    peaks: dict[date, LongWeekend],
    cons: list[str],
) -> int:
    """Add a con for each soft preference the option breaks; return how many."""
    before = len(cons)
    prefs = c.travel.family_flights
    window = f"{prefs.earliest:%H:%M}-{prefs.latest:%H:%M}"
    for leg in legs:
        if leg.mode != "flight":
            continue
        if leg.who in ("family", "everyone"):
            if prefs.weekend and leg.day.weekday() < 5:
                cons.append(f"Paula and Basia fly on a weekday ({leg.day:%a %d %b})")
            if leg.choice is not None and not (
                prefs.earliest <= leg.choice.depart.time() <= prefs.latest
            ):
                cons.append(
                    f"Paula and Basia's flight leaves at {leg.choice.depart:%H:%M}, "
                    f"outside {window}"
                )
        if leg.who in ("Martin", "everyone") and not c.day_off(leg.day):
            cons.append(f"Martin flies on a working day ({leg.day:%a %d %b}): unpaid hours")
        if leg.day in peaks:
            lw = peaks[leg.day]
            cons.append(
                f"Flight on {leg.day:%a %d %b} falls on a long weekend in {lw.country} "
                f"({lw.name}): usually dearer"
            )
    by_day: dict[date, list[str]] = {}
    for h in c.holidays:
        by_day.setdefault(h.day, []).append(f"{h.country} {h.name}".strip())
    martin = [d for d in _days(w.start, w.end) if d in by_day]
    family = [d for d in _days(fam_start, fam_end) if d in by_day]
    for who, days in (("Martin", martin), ("Paula and Basia", family)):
        if days:
            listed = ", ".join(f"{d:%d %b} ({'/'.join(by_day[d])})" for d in days)
            cons.append(f"{who} in Italy on public holidays: {listed}")
    return len(cons) - before


def build_options(
    c: Constraints,
    accommodation: AccommodationFile,
    transport: OptionsFile,
    windows: list[Window],
) -> list[Option]:
    house = next((a for a in accommodation.accommodation if a.preferred), None)
    if house is None:
        raise ValueError("accommodation.yaml needs one place with preferred: true")
    alternatives = [a for a in accommodation.accommodation if not a.preferred]
    tiers = c.travel.route_tiers

    family_blocks = [(p.start, p.end + timedelta(days=1)) for p in c.family_away()]
    peaks = peak_days(c.holidays) if c.travel.avoid_long_weekends else {}
    result: list[Option] = []
    for w in windows:
        house_free = _free_ranges(house, w.start, w.end)
        # Nights the family can be at the house: house free, and nobody needed in Poland.
        family_ranges = _subtract(house_free, family_blocks)
        if not family_ranges:
            continue
        hs, he = max(family_ranges, key=lambda r: r[1] - r[0])
        before, after = (hs - w.start).days, (w.end - he).days
        solo = before + after
        if solo > c.solo_max_days:
            continue
        if c.onward is not None:
            # Everyone flies on together, so the family must stay until the end.
            if after:
                continue
            away_end = w.end + timedelta(days=c.onward.nights)
            busy = [*c.martin_away(), *c.family_away()]
            if any(p.start < away_end and w.end <= p.end for p in busy):
                continue

        # Martin's nights without the family: at the house when it is free, else elsewhere.
        solo_segments = [(w.start, hs)] * bool(before) + [(he, w.end)] * bool(after)
        elsewhere = _subtract(solo_segments, house_free)
        elsewhere_nights = sum((e - s).days for s, e in elsewhere)
        solo_place = None
        if elsewhere:
            places = [a for a in alternatives if all(_free(a, s, e) for s, e in elsewhere)]
            if not places:
                continue
            solo_place = min(places, key=_price)
        house_nights = (he - hs).days + solo - elsewhere_nights

        modes = [False] + [True] * _car_allowed(c, w)
        for drive in modes:
            legs = _legs(c, transport, w, hs, he, drive)
            pros: list[str] = []
            cons: list[str] = []

            cost = 0.0
            if house.price_per_night_eur is None:
                cons.append(f"{house.name}: price per night unknown, not in total")
            else:
                cost += house_nights * house.price_per_night_eur
            if solo_place is not None:
                if solo_place.price_per_night_eur is None:
                    cons.append(f"{solo_place.name}: price per night unknown, not in total")
                else:
                    cost += elsewhere_nights * solo_place.price_per_night_eur

            martin_h = sum(leg.hours or 0 for leg in legs if leg.who in ("Martin", "everyone"))
            family_h = sum(leg.hours or 0 for leg in legs if leg.who in ("family", "everyone"))
            for leg in legs:
                if leg.missing:
                    cons.append(
                        f"No direct flight on your routes for {leg.who} ({leg.direction}, "
                        f"{leg.day}): ask for an alternative route"
                    )
                if leg.choice is not None:
                    cost += leg.choice.price_eur
                    if leg.choice.checked_on is None:
                        cons.append(
                            f"{leg.choice.carrier} {leg.choice.id} on {leg.day} not checked "
                            "live yet"
                        )

            if c.onward is not None:
                pros.append(f"Continues to {c.onward.name} for {c.onward.nights} nights, then home")
            if drive:
                pros.append("Martin drives and has the car in Italy; Paula and Basia fly")
                cons.append("Car costs (fuel, tolls) not in total")
            if solo:
                where = []
                if solo - elsewhere_nights:
                    where.append(f"{solo - elsewhere_nights} at {house.name}")
                if solo_place is not None:
                    where.append(f"{elsewhere_nights} at {solo_place.name}")
                cons.append(f"Martin alone for {solo} nights ({', '.join(where)})")
            else:
                pros.append(f"Family together at {house.name} for the whole stay")
            for fp in c.family:
                if fp.mode == "together" and fp.start < w.end and w.start <= fp.end and solo:
                    cons.append(f"Family wanted to travel together {fp.start} to {fp.end}")
            for p in c.presence:
                if p.strength != "pref" or p.where in ("IT", "any"):
                    continue
                martin_misses = "Martin" in p.who and p.start < w.end and w.start <= p.end
                family_misses = (
                    bool({"Paula", "Basia"} & set(p.who)) and p.start < he and hs <= p.end
                )
                if martin_misses or family_misses:
                    cons.append(f"Misses '{p.title or 'preferred event'}' on {p.start}")
            if w.office_covered:
                pros.append(f"Covers {len(w.office_covered)} required office period(s)")
            fam_out = next(
                (g.day for g in legs if g.who == "family" and g.direction == "outbound"), hs
            )
            fam_back = next(
                (g.day for g in legs if g.who == "family" and g.direction == "return"), he
            )
            soft = _soft_cons(c, legs, w, fam_out, fam_back, peaks, cons)
            if (fam_out, fam_back) != (hs, he):
                whole = f"Family together at {house.name} for the whole stay"
                pros[:] = [
                    f"Family at {house.name} {fam_out:%d %b} to {fam_back:%d %b} "
                    "(flight days moved to suit Paula and Basia)"
                    if x == whole
                    else x
                    for x in pros
                ]

            used = {leg.tier for leg in legs if leg.tier is not None}
            if used == {1}:
                pros.append("All flights on your first-choice routes")
            for t in sorted(used - {1}):
                if tiers and t <= len(tiers):
                    cons.append(f"Uses route choice {t}: {tiers[t - 1].name}")

            result.append(
                Option(
                    w,
                    house,
                    hs,
                    he,
                    solo_place,
                    solo,
                    drive,
                    legs,
                    round(cost, 2),
                    round(martin_h, 2),
                    round(family_h, 2),
                    pros,
                    cons,
                    family_start=fam_out,
                    family_end=fam_back,
                    soft=soft,
                )
            )
    return result


def shortlist(options: list[Option], n: int = 3, min_days_apart: int = 3) -> list[Option]:
    """Pick up to n good options whose departure days are spread out.

    Timing first: complete journeys, family together, car when allowed, best route
    choice, least door-to-door time. Cost only breaks ties.
    """
    ranked = sorted(
        options,
        key=lambda o: (
            len(o.missing_legs),
            not o.family_together,
            not o.martin_drives,
            o.worst_tier,
            o.soft,
            o.travel_hours,
            o.total_cost_eur,
            o.window.start,
        ),
    )
    picked: list[Option] = []
    for o in ranked:
        if all(abs((o.window.start - p.window.start).days) >= min_days_apart for p in picked):
            picked.append(o)
        if len(picked) == n:
            break
    return picked
