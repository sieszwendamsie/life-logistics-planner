"""Which flight times can work, per route, before searching (`planner routes`).

The door-to-door rules decide which departure and arrival times can ever be used,
so a search only needs flights inside these windows. Paula and Basia: leave home
after `family_flights.leave_home_after`, home by `arrive_home_by`, with a lift or
taxi on the Polish side and a drive on the Italian side. Martin alone: leave home
after `leave_home_after`; far airports need a bus or train (not known in advance).
"""

from dataclasses import dataclass
from datetime import datetime, time, timedelta

from planner.models import Travel

DAY = datetime(2000, 1, 1)


@dataclass
class RouteWindow:
    origin: str
    destination: str
    direction: str  # outbound (to Italy) or return
    tier: int
    family_depart_after: time | None  # None: the time to/from the airport is unknown
    family_arrive_by: time | None
    martin_depart_after: time | None
    note: str = ""

    @property
    def family_possible(self) -> bool:
        a, b = self.family_depart_after, self.family_arrive_by
        return a is None or b is None or a < b


def _hours(travel: Travel, airport: str, family: bool, italy: bool) -> float | None:
    if italy:
        drive = travel.italy_drives.get(airport)
        return drive.hours if drive else travel.transfer_hours.get(airport)
    ride = (travel.family_lifts.get(airport) if family else None) or travel.home_rides.get(airport)
    if ride:
        return ride.hours
    if not family and airport not in travel.home_airports:
        return None  # Martin needs a live-checked bus or train
    return travel.transfer_hours.get(airport)


def _at(start: time, hours: float) -> time:
    return (datetime.combine(DAY, start) + timedelta(hours=hours)).time()


def route_windows(travel: Travel) -> list[RouteWindow]:
    prefs = travel.family_flights
    margin, buffer = travel.airport_margin_hours, travel.arrival_buffer_hours
    result = []
    for i, tier in enumerate(travel.route_tiers, start=1):
        for pl in tier.origins:
            for it in tier.destinations:
                for direction in ("outbound", "return"):
                    out = direction == "outbound"
                    first, last = (pl, it) if out else (it, pl)
                    h_first_f = _hours(travel, first, True, not out)
                    h_last_f = _hours(travel, last, True, out)
                    h_first_m = _hours(travel, first, False, not out)
                    fam_dep = (
                        _at(prefs.leave_home_after, h_first_f + margin)
                        if h_first_f is not None
                        else None
                    )
                    fam_arr = (
                        _at(prefs.arrive_home_by, -(h_last_f + buffer))
                        if h_last_f is not None
                        else None
                    )
                    m_dep = (
                        _at(travel.leave_home_after, h_first_m + margin)
                        if h_first_m is not None
                        else None
                    )
                    note = "" if h_first_m is not None else "Martin: bus/train to check"
                    result.append(
                        RouteWindow(first, last, direction, i, fam_dep, fam_arr, m_dep, note)
                    )
    return result


def ryanair_month_url(origin: str, destination: str, month: str) -> str:
    """Ryanair's own fares API: the cheapest flight per day, with times, for a month."""
    return (
        f"https://www.ryanair.com/api/farfnd/v4/oneWayFares/{origin}/{destination}/"
        f"cheapestPerDay?outboundMonthOfDate={month}-01&currency=EUR"
    )


def table(windows: list[RouteWindow], month: str | None = None) -> str:
    def t(x: time | None) -> str:
        return f"{x:%H:%M}" if x else "  ?  "

    lines = ["tier route    dir       P+B depart after  P+B land by  Martin depart after"]
    for w in windows:
        fam = f"{t(w.family_depart_after)}             {t(w.family_arrive_by)}      "
        if not w.family_possible:
            fam = "never fits (05:00-20:00)             "
        lines.append(
            f"{w.tier:>4} {w.origin}-{w.destination}  {w.direction:<8}  {fam}"
            f"{t(w.martin_depart_after)} {w.note}"
        )
        if month:
            lines.append(f"       {ryanair_month_url(w.origin, w.destination, month)}")
    return "\n".join(lines)
