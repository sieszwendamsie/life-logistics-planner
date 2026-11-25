"""Turn date windows into full options: where to stay, who travels when, and cost.

Rules (see docs/spec.md, step 3):
- The family house (the preferred accommodation) must be free for most of the stay.
  Without it, the family does not travel and the window is dropped.
- If the house is free for only part of the window, Martin stays alone in another
  place before the family arrives and/or after it leaves, for at most
  `solo_max_days` nights in total.
- Each journey uses the cheapest collected option for that direction and day. A
  missing journey does not drop the option; it is listed as a con so it can be
  researched.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from planner.models import (
    Accommodation,
    AccommodationFile,
    Constraints,
    OptionsFile,
    TransportOption,
)
from planner.windows import Window

Who = Literal["everyone", "Martin", "family"]
Direction = Literal["outbound", "return"]


@dataclass
class Leg:
    who: Who
    direction: Direction
    day: date
    choice: TransportOption | None


@dataclass
class Option:
    window: Window
    house: Accommodation
    house_start: date
    house_end: date
    solo_place: Accommodation | None
    solo_nights: int
    legs: list[Leg]
    total_cost_eur: float
    travel_hours: float
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)

    @property
    def family_together(self) -> bool:
        return self.solo_nights == 0

    @property
    def missing_legs(self) -> list[Leg]:
        return [leg for leg in self.legs if leg.choice is None]


def _free(place: Accommodation, start: date, end: date) -> bool:
    """True if the place is free for the nights start .. end-1."""
    return any(r.start <= start and end <= r.end for r in place.available)


def _house_cover(house: Accommodation, w: Window) -> tuple[date, date] | None:
    best: tuple[date, date] | None = None
    for r in house.available:
        s, e = max(w.start, r.start), min(w.end, r.end)
        if s < e and (best is None or (e - s) > (best[1] - best[0])):
            best = (s, e)
    return best


def _cheapest(transport: OptionsFile, direction: Direction, day: date) -> TransportOption | None:
    found = [o for o in transport.options if o.direction == direction and o.depart.date() == day]
    return min(found, key=lambda o: o.price_eur, default=None)


def _price(place: Accommodation) -> float:
    return place.price_per_night_eur if place.price_per_night_eur is not None else float("inf")


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

    result: list[Option] = []
    for w in windows:
        cover = _house_cover(house, w)
        if cover is None:
            continue
        hs, he = cover
        before, after = (hs - w.start).days, (w.end - he).days
        solo = before + after
        if solo > c.solo_max_days:
            continue

        solo_place = None
        if solo:
            segments = [(w.start, hs)] * bool(before) + [(he, w.end)] * bool(after)
            places = [a for a in alternatives if all(_free(a, s, e) for s, e in segments)]
            if not places:
                continue
            solo_place = min(places, key=_price)

        plan: list[tuple[Who, Direction, date]]
        if before:
            plan = [("Martin", "outbound", w.start), ("family", "outbound", hs)]
        else:
            plan = [("everyone", "outbound", w.start)]
        if after:
            plan += [("family", "return", he), ("Martin", "return", w.end)]
        else:
            plan += [("everyone", "return", w.end)]
        legs = [Leg(who, d, day, _cheapest(transport, d, day)) for who, d, day in plan]

        pros: list[str] = []
        cons: list[str] = []
        house_nights = (he - hs).days
        cost = 0.0
        if house.price_per_night_eur is None:
            cons.append(f"{house.name}: price per night unknown, not in total")
        else:
            cost += house_nights * house.price_per_night_eur
        if solo_place is not None:
            if solo_place.price_per_night_eur is None:
                cons.append(f"{solo_place.name}: price per night unknown, not in total")
            else:
                cost += solo * solo_place.price_per_night_eur
        hours = 0.0
        for leg in legs:
            if leg.choice is None:
                cons.append(f"No {leg.direction} journey collected for {leg.who} on {leg.day}")
            else:
                cost += leg.choice.price_eur
                hours += (leg.choice.arrive - leg.choice.depart).total_seconds() / 3600

        if solo:
            cons.append(f"Martin alone for {solo} nights at {solo_place.name}")  # type: ignore[union-attr]
        else:
            pros.append(f"Family together at {house.name} for the whole stay")
        for fp in c.family:
            if fp.mode == "together" and fp.start < w.end and w.start <= fp.end and solo:
                cons.append(f"Family wanted to travel together {fp.start} to {fp.end}")
        if w.office_covered:
            pros.append(f"Covers {len(w.office_covered)} required office period(s)")

        result.append(
            Option(
                w,
                house,
                hs,
                he,
                solo_place,
                solo,
                legs,
                round(cost, 2),
                round(hours, 2),
                pros,
                cons,
            )
        )
    return result


def shortlist(options: list[Option], n: int = 3, min_days_apart: int = 3) -> list[Option]:
    """Pick up to n good options whose departure days are spread out.

    Ranking: fewest missing journeys, family together, lowest cost, shortest travel.
    """
    ranked = sorted(
        options,
        key=lambda o: (
            len(o.missing_legs),
            not o.family_together,
            o.total_cost_eur,
            o.travel_hours,
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
