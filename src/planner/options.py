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
from datetime import date, datetime, timedelta
from typing import Literal

from planner.costs import round_trip
from planner.holidays import LongWeekend, peak_days
from planner.models import (
    Accommodation,
    AccommodationFile,
    Constraints,
    GroundOption,
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
    # Bus or train between home and a far airport (live-checked), if needed.
    transfer: GroundOption | None = None
    needs_transfer: bool = False

    @property
    def missing(self) -> bool:
        return self.mode == "flight" and self.choice is None

    @property
    def open_transfer(self) -> bool:
        return self.needs_transfer and self.transfer is None

    @property
    def people(self) -> int:
        """Seats: Martin and Paula; Basia flies on Paula's lap."""
        return {"Martin": 1, "family": 1, "everyone": 2}[self.who]

    @property
    def with_infant(self) -> bool:
        return self.who in ("family", "everyone")


@dataclass
class Journey:
    """One person's (or group's) trip from door to door."""

    who: Who
    direction: Direction
    day: date
    start: str  # e.g. "home"
    end: str  # e.g. "Faenza" or "the office"
    leave: datetime | None = None
    arrive: datetime | None = None
    hours: float | None = None
    how: str = ""  # e.g. "taxi, Ryanair FR 3594 POZ-BGY, hire car"


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
    # Hire cars or trains this option needs whose price was not checked live.
    open_ground: int = 0
    # Cost by kind (flights, car hire, driving, taxis, trains and buses...).
    costs: dict[str, float] = field(default_factory=dict)
    # Door to door, per journey: from home to Faenza (or the office) and back.
    journeys: list["Journey"] = field(default_factory=list)

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


def _transfer(
    transport: OptionsFile, travel: Travel, o: TransportOption, infant: bool = False
) -> tuple[bool, GroundOption | None]:
    """Bus or train between home and the Polish or German end of a flight.

    Returns (needed, best checked one). Outbound: the latest one that leaves home
    after `leave_home_after` and reaches the airport `airport_margin_hours` before
    take-off. Return: the first one leaving 45 minutes after landing.
    """
    if o.direction == "outbound":
        airport = o.origin
    elif o.direction in ("return", "home"):
        airport = o.destination
    else:
        return False, None
    if airport in travel.home_airports:
        return False, None
    if infant and airport in travel.family_lifts:
        return False, None  # a relative drives them
    margin = timedelta(hours=travel.airport_margin_hours)
    fits = []
    for g in transport.ground:
        if g.kind != "transfer" or g.airport != airport or g.checked_on is None:
            continue
        if g.depart is None or g.arrive is None:
            continue
        if o.direction == "outbound":
            ok = g.arrive <= o.depart - margin and g.depart.time() >= travel.leave_home_after
            ok = ok and g.depart.date() == o.depart.date()
        else:
            ok = g.depart >= o.arrive + timedelta(minutes=45)
            ok = ok and g.depart.date() == o.arrive.date()
        if ok:
            fits.append(g)
    if not fits:
        return True, None
    if o.direction == "outbound":
        return True, max(fits, key=lambda g: (g.depart, -g.price_eur))
    return True, min(fits, key=lambda g: (g.arrive, g.price_eur))


def _family_door(travel: Travel, o: TransportOption) -> tuple[datetime | None, datetime | None]:
    """Paula and Basia's door to door: (leave home, arrive home), None if unknown.

    Polish side: a relative's lift (`family_lifts`) or a taxi (`home_rides`).
    Italian side: the drive to Faenza (`italy_drives`), else `transfer_hours`.
    """
    out = o.direction == "outbound"
    pl_port, it_port = (o.origin, o.destination) if out else (o.destination, o.origin)
    lift = travel.family_lifts.get(pl_port) or travel.home_rides.get(pl_port)
    drive = travel.italy_drives.get(it_port)
    pl_h = lift.hours if lift else travel.transfer_hours.get(pl_port)
    it_h = drive.hours if drive else travel.transfer_hours.get(it_port)
    margin = timedelta(hours=travel.airport_margin_hours)
    buffer = timedelta(hours=travel.arrival_buffer_hours)
    first, last = (pl_h, it_h) if out else (it_h, pl_h)
    leave = o.depart - margin - timedelta(hours=first) if first is not None else None
    arrive = o.arrive + buffer + timedelta(hours=last) if last is not None else None
    return leave, arrive


def _family_window_ok(travel: Travel, o: TransportOption) -> bool:
    """Hard rule: leave home after 05:00 and be home by 20:00 on the flight day."""
    prefs = travel.family_flights
    leave, arrive = _family_door(travel, o)
    day = o.depart.date()
    if leave is not None and leave < datetime.combine(day, prefs.leave_home_after):
        return False
    return arrive is None or arrive <= datetime.combine(day, prefs.arrive_home_by)


def _flight_hours(travel: Travel, o: TransportOption, t: GroundOption | None) -> float:
    if t is None or t.depart is None or t.arrive is None:
        return _door_hours(travel, o)
    th = travel.transfer_hours
    if o.direction == "outbound":
        return (o.arrive - t.depart).total_seconds() / 3600 + th.get(o.destination, 0)
    return (t.arrive - o.depart).total_seconds() / 3600 + th.get(o.origin, 0)


def _flight(
    transport: OptionsFile,
    travel: Travel,
    who: Who,
    d: Direction,
    day: date,
    onward: OnwardTrip | None = None,
) -> Leg:
    best: tuple[tuple, Leg] | None = None
    for o in transport.options:
        if o.direction != d or o.depart.date() != day:
            continue
        if travel.direct_only and o.stops:
            continue
        tier = _tier(travel, o, onward)
        if tier is None:
            continue
        infant = who != "Martin"
        if infant and not _family_window_ok(travel, o):
            continue
        needed, t = _transfer(transport, travel, o, infant)
        hours = _flight_hours(travel, o, t)
        if infant:
            leave, arrive = _family_door(travel, o)
            if leave is not None and arrive is not None:
                hours = (arrive - leave).total_seconds() / 3600
        leg = Leg(who, d, day, "flight", o, tier, round(hours, 2), t, needed)
        # A flight you cannot get to with a checked bus or train comes last.
        key = (leg.open_transfer, tier, hours, o.price_eur)
        if best is None or key < best[0]:
            best = (key, leg)
    if best is None:
        return Leg(who, d, day)
    return best[1]


def _family_flight(
    transport: OptionsFile, travel: Travel, d: Direction, day: date, lo: date, hi: date
) -> Leg:
    """Paula and Basia's flight: the best day between lo and hi (both included).

    Flights that break the 05:00 / 20:00 door-to-door limits are never used.
    Then: weekend first, then the shortest door-to-door time (to the half hour),
    a departure inside the preferred hours, route choice, the fewest days moved
    and price.
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
            round((leg.hours or 0) * 2),
            off_hours,
            leg.tier or 0,
            abs((cand - day).days),
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


def _ground(
    c: Constraints,
    transport: OptionsFile,
    legs: list[Leg],
    w: Window,
    fam_out: date,
    fam_back: date,
) -> list[tuple[GroundOption | None, str]]:
    """Hire car and trains in Italy when Martin flies, with their checked prices.

    Paula and Basia always need a car. Martin alone takes the train when he flies
    to one of `travel.train_airports` (e.g. Bologna), otherwise he hires a car.
    """
    trains = c.travel.train_airports
    solo_out = next((g for g in legs if g.who == "Martin" and g.direction == "outbound"), None)
    solo_back = next((g for g in legs if g.who == "Martin" and g.direction == "return"), None)
    needs: list[tuple[str, date, date | None, str]] = []
    car_start, car_end = w.start, w.end
    if solo_out and solo_out.choice and solo_out.choice.destination in trains:
        airport = solo_out.choice.destination
        needs.append(("train", w.start, None, f"Martin: train from {airport}"))
        needs.append(("train", fam_out, None, "Martin: train to collect the hire car"))
        car_start = fam_out
    if solo_back and solo_back.choice and solo_back.choice.origin in trains:
        needs.append(("train", w.end, None, f"Martin: train to {solo_back.choice.origin}"))
        car_end = fam_back
    needs.insert(
        0, ("car_hire", car_start, car_end, f"Hire car {car_start:%d %b} to {car_end:%d %b}")
    )
    pick, drop = _hire_airports(legs, car_start, car_end)

    found: list[tuple[GroundOption | None, str]] = []
    for kind, start, end, label in needs:
        match = [
            g
            for g in transport.ground
            if g.kind == kind
            and g.start == start
            and g.checked_on is not None
            and (kind == "train" or g.end == end)
            and (kind == "train" or g.pick_up in (None, pick))
            and (kind == "train" or g.drop_off in (None, drop))
        ]
        best = min(match, key=lambda g: g.price_eur) if match else None
        if best is not None and best.where:
            label = f"{label} ({best.where})"
        found.append((best, label))
    return found


def _hire_airports(legs: list[Leg], start: date, end: date) -> tuple[str | None, str | None]:
    """Airports where the hire car is picked up (arrival on `start`) and dropped off."""
    flights = [g for g in legs if g.mode == "flight" and g.choice is not None]
    pick = next(
        (g.choice.destination for g in flights if g.direction == "outbound" and g.day == start),
        None,
    )
    drop = next(
        (g.choice.origin for g in flights if g.direction == "return" and g.day == end),
        None,
    )
    return pick, drop


def _by_airline(table: dict[str, float], carrier: str) -> float | None:
    """Fee for an airline, matching the start of the carrier name (e.g. 'Ryanair FR 3594')."""
    for name, eur in table.items():
        if carrier.lower().startswith(name.lower()):
            return eur
    return None


def _uses_train(c: Constraints, leg: Leg) -> bool:
    """Martin alone, flying into a train airport (when he has no car with him)."""
    if leg.who != "Martin" or leg.choice is None or leg.mode != "flight":
        return False
    port = leg.choice.destination if leg.direction == "outbound" else leg.choice.origin
    return port in c.travel.train_airports


def _journey(c: Constraints, transport: OptionsFile, leg: Leg) -> Journey:
    """Door to door for one leg: Polish side, flight, Italian side."""
    t = c.travel
    out = leg.direction == "outbound"
    home, italy = t.home_name, t.italy_home_name
    start, end = (home, italy) if out else (italy, home)
    if leg.mode == "car":
        hours = t.car.drive_hours if t.car else None
        return Journey(leg.who, leg.direction, leg.day, start, end, hours=hours, how="own car")
    o = leg.choice
    if o is None:
        return Journey(leg.who, leg.direction, leg.day, start, end, how="flight to find")
    pl_port, it_port = (o.origin, o.destination) if out else (o.destination, o.origin)
    margin = timedelta(hours=t.airport_margin_hours)
    how: list[str] = []
    # Polish side.
    ride = t.home_rides.get(pl_port)
    lift = t.family_lifts.get(pl_port) if leg.with_infant else None
    pl_leave = pl_arrive = None
    if leg.transfer is not None and leg.transfer.depart and leg.transfer.arrive:
        how.append(leg.transfer.detail.split(" ")[0] or "bus")
        pl_leave, pl_arrive = leg.transfer.depart, leg.transfer.arrive
    elif lift is not None or ride is not None:
        how.append("lift" if lift is not None else "taxi")
        ride = lift or ride
        assert ride is not None
        if out:
            pl_leave = o.depart - margin - timedelta(hours=ride.hours)
        else:
            pl_arrive = o.arrive + timedelta(hours=t.arrival_buffer_hours + ride.hours)
    else:
        h = timedelta(hours=t.transfer_hours.get(pl_port, 0))
        pl_leave = o.depart - margin - h if out else None
        pl_arrive = None if out else o.arrive + timedelta(hours=t.arrival_buffer_hours) + h
    how.append(f"{o.carrier} {o.origin}-{o.destination}")
    # Italian side.
    drive = t.italy_drives.get(it_port)
    train = None
    if _uses_train(c, leg):
        train = next(
            (
                g
                for g in transport.ground
                if g.kind == "train" and g.start == leg.day and g.depart and g.arrive
            ),
            None,
        )
    it_leave = it_arrive = None
    if train is not None:
        how.append("train")
        if out:
            it_arrive = train.arrive + timedelta(hours=t.station_to_home_hours)
        else:
            it_leave = train.depart - timedelta(hours=t.station_to_home_hours)
    elif drive is not None:
        how.append("car")
        if out:
            it_arrive = o.arrive + timedelta(hours=t.arrival_buffer_hours + drive.hours)
        else:
            it_leave = o.depart - margin - timedelta(hours=drive.hours)
    else:
        h = timedelta(hours=t.transfer_hours.get(it_port, 0))
        if out:
            it_arrive = o.arrive + timedelta(hours=t.arrival_buffer_hours) + h
        else:
            it_leave = o.depart - margin - h
    leave, arrive = (pl_leave, it_arrive) if out else (it_leave, pl_arrive)
    if out and leg.who in ("Martin", "everyone") and arrive is not None:
        working = not c.day_off(arrive.date())
        if working and arrive.time() <= t.office_if_arriving_by:
            end = t.office_name
    hours = (arrive - leave).total_seconds() / 3600 if leave and arrive else None
    return Journey(
        leg.who,
        leg.direction,
        leg.day,
        start,
        end,
        leave,
        arrive,
        round(hours, 2) if hours is not None else None,
        ", ".join(how),
    )


def _extras(
    c: Constraints, legs: list[Leg], w: Window, drive: bool
) -> tuple[float, float, list[str]]:
    """Taxis to Polish airports and drives between Italian airports and Faenza.

    Returns (taxi cost, driving cost, notes). Martin drives to fetch Paula and
    Basia and back (two drives), or one drive when he travels himself or leaves
    Italy that day.
    """
    t = c.travel
    taxis = driving = 0.0
    notes: list[str] = []
    l_per_km = t.car.costs.l_per_100km / 100 if t.car else 0.06
    martin_out = next((g for g in legs if g.who == "Martin" and g.direction == "outbound"), None)
    has_car_early = drive or not (martin_out and _uses_train(c, martin_out))
    count: dict[str, int] = {}
    for leg in legs:
        o = leg.choice
        if leg.mode != "flight" or o is None:
            continue
        out = leg.direction == "outbound"
        pl_port, it_port = (o.origin, o.destination) if out else (o.destination, o.origin)
        lift = leg.with_infant and pl_port in t.family_lifts
        if leg.transfer is None and not lift and pl_port in t.home_rides:
            taxis += t.home_rides[pl_port].price_eur
        if it_port not in t.italy_drives or _uses_train(c, leg):
            continue
        if leg.who != "family":
            n = 1
        elif out:
            n = 2 if has_car_early else 1
        else:
            n = 1 if (leg.day == w.end or not has_car_early) else 2
        count[it_port] = count.get(it_port, 0) + n
    for port, n in count.items():
        d = t.italy_drives[port]
        fuel = d.km * l_per_km * t.italy_fuel_eur_per_l
        driving += n * (d.toll_eur + fuel)
        notes.append(
            f"{n} drive(s) {port} to or from Faenza: €{n * (d.toll_eur + fuel):.0f} "
            f"(toll €{d.toll_eur:.2f} + fuel €{fuel:.0f} each, {d.km:.0f} km)"
        )
    return round(taxis, 2), round(driving, 2), notes


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

            costs: dict[str, float] = {}

            def add(kind: str, eur: float, costs: dict[str, float] = costs) -> None:
                costs[kind] = round(costs.get(kind, 0) + eur, 2)

            if house.price_per_night_eur is None:
                cons.append(f"{house.name}: price per night unknown, not in total")
            else:
                add("Accommodation", house_nights * house.price_per_night_eur)
            if solo_place is not None:
                if solo_place.price_per_night_eur is None:
                    cons.append(f"{solo_place.name}: price per night unknown, not in total")
                else:
                    add("Accommodation", elsewhere_nights * solo_place.price_per_night_eur)

            open_ground = 0
            for leg in legs:
                if leg.missing:
                    cons.append(
                        f"No direct flight on your routes for {leg.who} ({leg.direction}, "
                        f"{leg.day}): ask for an alternative route"
                    )
                if leg.transfer is not None:
                    t = leg.transfer
                    add("Trains and buses", t.price_eur * leg.people)
                    cons.append(
                        f"{leg.who}: {t.detail} ({t.depart:%H:%M} to {t.arrive:%H:%M}, "
                        f"€{t.price_eur * leg.people:.0f}, checked {t.checked_on:%d %b}; in total)"
                    )
                elif leg.open_transfer:
                    open_ground += 1
                    port = (
                        leg.choice.origin if leg.direction == "outbound" else leg.choice.destination
                    )
                    cons.append(
                        f"{leg.who}: no live-checked bus or train to {port} that leaves home "
                        f"after {c.travel.leave_home_after:%H:%M} and arrives "
                        f"{c.travel.airport_margin_hours:g} h before the flight"
                    )
                if leg.choice is not None:
                    add("Flights", leg.choice.price_eur / leg.choice.seats * leg.people)
                    carrier = leg.choice.carrier
                    if leg.with_infant and c.travel.infants:
                        fee = _by_airline(c.travel.infant_fee_eur, carrier)
                        if fee is None:
                            open_ground += 1
                            cons.append(f"{carrier}: infant fee not checked yet")
                        else:
                            add("Infant fees", fee * c.travel.infants)
                    bags = 0 if drive else leg.people * c.travel.checked_bags_per_adult
                    if bags:
                        fee = leg.choice.bag_eur
                        if fee is None:
                            fee = _by_airline(c.travel.checked_bag_eur, carrier)
                        if fee is None:
                            open_ground += 1
                            cons.append(f"{carrier}: 20 kg bag price not checked yet")
                        else:
                            add("Checked bags", fee * bags)
                    if leg.choice.checked_on is None:
                        cons.append(
                            f"{leg.choice.carrier} {leg.choice.id} on {leg.day} not checked "
                            "live yet"
                        )

            if c.onward is not None:
                pros.append(f"Continues to {c.onward.name} for {c.onward.nights} nights, then home")
            car = c.travel.car
            if drive and car is not None:
                pros.append("Martin drives and has the car in Italy; Paula and Basia fly")
                drive_cost = round_trip(car.costs, w.start, w.end)
                add("Own car: fuel, tolls, vignettes", drive_cost.total_eur)
                cons.append(drive_cost.text() + " (in total)")
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
            if not drive and c.onward is None:
                for g, label in _ground(c, transport, legs, w, fam_out, fam_back):
                    if g is None:
                        open_ground += 1
                        cons.append(f"{label}: price not checked live yet")
                    else:
                        add("Car hire" if g.kind == "car_hire" else "Trains and buses", g.price_eur)
                        cons.append(
                            f"{label}: €{g.price_eur:.0f} ({g.detail}, checked "
                            f"{g.checked_on:%d %b}; in total)"
                        )
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

            journeys = [_journey(c, transport, leg) for leg in legs]
            for leg, j in zip(legs, journeys, strict=True):
                if j.hours is not None:
                    leg.hours = j.hours
            martin_h = sum(g.hours or 0 for g in legs if g.who in ("Martin", "everyone"))
            family_h = sum(g.hours or 0 for g in legs if g.who in ("family", "everyone"))
            taxis, driving, notes = _extras(c, legs, w, drive)
            if taxis:
                add("Taxis to and from airports", taxis)
            if driving:
                add("Driving in Italy: tolls, fuel", driving)
            cons.extend(f"{n} (in total)" for n in notes)

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
                    round(sum(costs.values()), 2),
                    round(martin_h, 2),
                    round(family_h, 2),
                    pros,
                    cons,
                    family_start=fam_out,
                    family_end=fam_back,
                    soft=soft,
                    open_ground=open_ground,
                    costs=costs,
                    journeys=journeys,
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
