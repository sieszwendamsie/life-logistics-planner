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


def _car_allowed(c: Constraints, w: Window) -> bool:
    car = c.travel.car
    if car is None or c.onward is not None or w.days < car.min_stay_days:
        return False
    lo, hi = w.start - timedelta(days=car.clear_days), w.end + timedelta(days=car.clear_days)
    return not any(t.start <= hi and lo <= t.end for t in c.other_travel)


def _price(place: Accommodation) -> float:
    return place.price_per_night_eur if place.price_per_night_eur is not None else float("inf")


def _legs(
    c: Constraints, transport: OptionsFile, w: Window, hs: date, he: date, drive: bool
) -> list[Leg]:
    travel = c.travel
    if drive:
        hours = travel.car.drive_hours if travel.car else None
        return [
            Leg("Martin", "outbound", w.start, "car", hours=hours),
            _flight(transport, travel, "family", "outbound", hs),
            _flight(transport, travel, "family", "return", he),
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
    return [_flight(transport, travel, who, d, day, c.onward) for who, d, day in plan]


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
