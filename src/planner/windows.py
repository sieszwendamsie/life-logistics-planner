"""Find feasible date windows for the next stay in Italy.

A window is a departure day and a return day. Its length in days is
(end - start), the number of nights away. A window is feasible when:

- it lies inside the planning horizon,
- its length is within the stay rules,
- it starts within the allowed gap after the last return (if known),
- it does not overlap any date Martin must be in Poznań or elsewhere outside
  Italy (`poznan_required`, and `presence` entries for Martin with #PL or #UK),
- it does not cut through a required office period (`office_required`, and
  #IT must entries for Martin): one that overlaps the window must lie fully
  inside it. Unless `stay_rules.travel_on_office_days` is set, Martin also
  does not travel on an office day: he arrives the day before at the latest.

Accommodation is checked later, when windows become options.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from planner.models import Constraints, DateRange


@dataclass(frozen=True)
class Window:
    start: date
    end: date
    office_covered: tuple[DateRange, ...]

    @property
    def days(self) -> int:
        return (self.end - self.start).days


def _overlaps(start: date, end: date, other: DateRange) -> bool:
    return start <= other.end and other.start <= end


def _contains(start: date, end: date, other: DateRange) -> bool:
    return start <= other.start and other.end <= end


def _start_range(c: Constraints) -> tuple[date, date]:
    if c.last_return is None:
        return c.horizon.start, c.horizon.end
    rules = c.stay_rules
    earliest = max(c.horizon.start, c.last_return + timedelta(days=rules.min_gap_days))
    latest = min(c.horizon.end, c.last_return + timedelta(days=rules.max_gap_days))
    return earliest, latest


def find_windows(c: Constraints) -> list[Window]:
    """All feasible windows, best first: most office periods covered, then earliest."""
    earliest, latest = _start_range(c)
    rules = c.stay_rules
    away, italy = c.martin_away(), c.martin_italy()
    found: list[Window] = []
    start = earliest
    while start <= latest:
        for length in range(rules.min_stay_days, rules.max_stay_days + 1):
            end = start + timedelta(days=length)
            if end > c.horizon.end:
                break
            if any(_overlaps(start, end, p) for p in away):
                continue
            office = [o for o in italy if _overlaps(start, end, o)]
            if any(not _contains(start, end, o) for o in office):
                continue
            if not rules.travel_on_office_days and any(
                start == o.start or end == o.end for o in office
            ):
                continue
            found.append(Window(start, end, tuple(office)))
        start += timedelta(days=1)
    found.sort(key=lambda w: (-len(w.office_covered), w.start, w.days))
    return found
