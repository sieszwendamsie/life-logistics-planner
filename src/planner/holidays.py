"""Public holidays: long weekends and holiday days.

A long weekend is a run of at least three days off in a row in one country:
weekends plus public holidays, with a single working "bridge" day between them
counted as off (many people take it). Flights on these days, and on the day
before, are usually more expensive, so the planner tries to avoid them.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from planner.models import Holiday


@dataclass(frozen=True)
class LongWeekend:
    country: str
    start: date
    end: date  # last day off, included
    name: str

    def peak_days(self) -> set[date]:
        """The days off plus the day before, when everyone travels."""
        days = (self.end - self.start).days + 1
        first = self.start - timedelta(days=1)
        return {first + timedelta(days=i) for i in range(days + 1)}


def long_weekends(holidays: list[Holiday]) -> list[LongWeekend]:
    result: list[LongWeekend] = []
    for country in ("PL", "IT"):
        mine = {h.day: h.name for h in holidays if h.country == country}

        def off(d: date, mine: dict[date, str] = mine) -> bool:
            return d.weekday() >= 5 or d in mine

        seen: set[date] = set()
        for day in sorted(mine):
            if day in seen:
                continue
            start = end = day
            while True:
                before = start - timedelta(days=1)
                bridge = start - timedelta(days=2)
                if off(before):
                    start = before
                elif off(bridge) and before.weekday() < 5:
                    start = bridge
                else:
                    break
            while True:
                after = end + timedelta(days=1)
                bridge = end + timedelta(days=2)
                if off(after):
                    end = after
                elif off(bridge) and after.weekday() < 5:
                    end = bridge
                else:
                    break
            span = {start + timedelta(days=i) for i in range((end - start).days + 1)}
            seen |= span
            if len(span) >= 3:
                names = sorted({mine[d] for d in span if d in mine and mine[d]})
                result.append(LongWeekend(country, start, end, ", ".join(names)))
    return sorted(result, key=lambda lw: lw.start)


def peak_days(holidays: list[Holiday]) -> dict[date, LongWeekend]:
    """Each day on which flying is likely expensive, with its long weekend."""
    days: dict[date, LongWeekend] = {}
    for lw in long_weekends(holidays):
        for d in lw.peak_days():
            days.setdefault(d, lw)
    return days
