"""Live Ryanair fares: one call per route and month, cached with source and check time.

Ryanair's own website calls the `farfnd` fare API to draw its month calendar. It
returns the cheapest flight per day with departure and arrival times (local) and a
price. This module asks that same API, so the data is the airline's own and live,
never a schedule site. Rules from Martin (docs/planning-rules.md):

- Every result keeps its source URL and the time it was checked.
- If the API cannot be reached or its answer looks wrong, raise `FareError` and say
  so. Never fill a gap with a guess; fall back to the browser steps in the
  `find-flights` skill.
- A cached answer is only reused while it is younger than `max_age`; its age is
  always shown.

The month view has no flight number and shows only the cheapest flight of the day,
so a day that fits the time windows is a *candidate*: confirm finalists on the
Ryanair select page (the `find-flights` skill) before proposing anything.
"""

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

CACHE_DIR = Path("data/cache/fares")
DEFAULT_MAX_AGE = timedelta(hours=12)
USER_AGENT = "Mozilla/5.0 (compatible; life-logistics-planner; personal use)"

Fetcher = Callable[[str], bytes]


class FareError(Exception):
    """The fares could not be read live. The message says why, in plain words."""


@dataclass(frozen=True)
class DayFare:
    origin: str
    destination: str
    depart: datetime  # local time at the origin airport
    arrive: datetime  # local time at the destination airport
    price_eur: float

    def fits(self, depart_after: time | None, arrive_by: time | None) -> bool:
        """True if the flight is inside the time window (None: no limit from that side)."""
        if depart_after is not None and self.depart.time() < depart_after:
            return False
        return not (arrive_by is not None and self.arrive.time() > arrive_by)


@dataclass(frozen=True)
class MonthFares:
    origin: str
    destination: str
    month: str  # YYYY-MM
    days: list[DayFare]
    source_url: str
    checked_at: datetime  # UTC
    from_cache: bool = False

    def age(self, now: datetime | None = None) -> timedelta:
        return (now or datetime.now(UTC)) - self.checked_at


def month_url(origin: str, destination: str, month: str) -> str:
    return (
        f"https://www.ryanair.com/api/farfnd/v4/oneWayFares/{origin}/{destination}/"
        f"cheapestPerDay?outboundMonthOfDate={month}-01&currency=EUR"
    )


def http_fetch(url: str) -> bytes:
    """GET with the standard library. Any failure becomes a FareError."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read()
    except urllib.error.HTTPError as err:
        hint = " (blocked or rate-limited)" if err.code in (403, 429) else ""
        raise FareError(f"Ryanair answered HTTP {err.code}{hint}") from err
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        raise FareError(f"could not reach Ryanair: {err}") from err


def parse_month(raw: bytes, origin: str, destination: str) -> list[DayFare]:
    """Read the cheapestPerDay answer. Raises FareError if its shape is not as expected."""
    try:
        fares = json.loads(raw)["outbound"]["fares"]
        days = []
        for f in fares:
            if f.get("unavailable") or f.get("soldOut"):
                continue
            price = f["price"]
            if price["currencyCode"] != "EUR":
                raise FareError(f"price is in {price['currencyCode']}, expected EUR")
            days.append(
                DayFare(
                    origin,
                    destination,
                    datetime.fromisoformat(f["departureDate"]),
                    datetime.fromisoformat(f["arrivalDate"]),
                    float(price["value"]),
                )
            )
    except (ValueError, KeyError, TypeError) as err:
        raise FareError(f"Ryanair's answer has an unexpected shape ({err!r})") from err
    return sorted(days, key=lambda d: d.depart)


def _cache_path(cache_dir: Path, origin: str, destination: str, month: str) -> Path:
    return cache_dir / f"{origin}-{destination}-{month}.json"


def _to_json(m: MonthFares) -> str:
    return json.dumps(
        {
            "source_url": m.source_url,
            "checked_at": m.checked_at.isoformat(),
            "days": [[d.depart.isoformat(), d.arrive.isoformat(), d.price_eur] for d in m.days],
        },
        indent=1,
    )


def _from_json(text: str, origin: str, destination: str, month: str) -> MonthFares:
    data = json.loads(text)
    days = [
        DayFare(origin, destination, datetime.fromisoformat(a), datetime.fromisoformat(b), p)
        for a, b, p in data["days"]
    ]
    return MonthFares(
        origin,
        destination,
        month,
        days,
        data["source_url"],
        datetime.fromisoformat(data["checked_at"]),
        from_cache=True,
    )


def month_fares(
    origin: str,
    destination: str,
    month: str,
    *,
    fetch: Fetcher = http_fetch,
    cache_dir: Path = CACHE_DIR,
    max_age: timedelta = DEFAULT_MAX_AGE,
    refresh: bool = False,
    now: datetime | None = None,
) -> MonthFares:
    """Fares for one route and month: from a fresh cache file, else live from Ryanair.

    Raises FareError when no live answer is possible and the cache is not fresh.
    A stale cache is never returned.
    """
    now = now or datetime.now(UTC)
    path = _cache_path(cache_dir, origin, destination, month)
    if not refresh and path.exists():
        try:
            cached = _from_json(path.read_text(encoding="utf-8"), origin, destination, month)
            if cached.age(now) <= max_age:
                return cached
        except (ValueError, KeyError, TypeError):
            pass  # unreadable cache file: ignore it and ask Ryanair
    url = month_url(origin, destination, month)
    days = parse_month(fetch(url), origin, destination)
    result = MonthFares(origin, destination, month, days, url, now)
    cache_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(_to_json(result), encoding="utf-8")
    return result


def describe(m: MonthFares, depart_after: time | None, arrive_by: time | None) -> list[str]:
    """Lines for the days of a month that fit the window, with source and check time."""
    age = "cached" if m.from_cache else "live"
    stamp = f"{m.checked_at:%Y-%m-%d %H:%M} UTC"
    lines = [f"{m.origin}-{m.destination} {m.month}: Ryanair farfnd, {age}, checked {stamp}"]
    fitting = [d for d in m.days if d.fits(depart_after, arrive_by)]
    if not m.days:
        lines.append("  no Ryanair flight on this route this month")
    elif not fitting:
        lines.append(f"  {len(m.days)} days with flights, none inside the time window")
    for d in fitting:
        day = f"{d.depart:%a %Y-%m-%d} {d.depart:%H:%M}-{d.arrive:%H:%M}"
        lines.append(f"  {day}  from {d.price_eur:.2f} EUR")
    return lines
