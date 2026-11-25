"""Build the visual report: scenarios, a timeline per person and a comparison.

`planner report` turns the same options as `planner scenarios` into one HTML page
(out/report.html). The maths stays here in Python; the template in
templates/report.html.j2 only draws what this module computes.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from planner.models import AccommodationFile, Constraints, OptionsFile
from planner.options import Leg, Option, build_options, shortlist
from planner.windows import find_windows

LABELS = "ABCDEFGHIJ"


@dataclass
class Scenario:
    back: date | None  # day back in Poznań after the current trip
    label: str  # e.g. the flight that brings Martin back
    earliest: date | None
    latest: date | None
    options: list[Option]


def scenario(
    base: Constraints,
    accommodation: AccommodationFile,
    transport: OptionsFile,
    back: date | None,
    label: str = "",
    top: int = 3,
    changes: dict[str, object] | None = None,
) -> Scenario:
    """Best next-stay options if Martin is back in Poznań on `back`.

    `changes` overrides top-level constraint fields for this scenario only, for
    example {"solo_max_days": 9} to see what a one-off exception would give.
    """
    update: dict[str, object] = dict(changes or {})
    if back:
        update["last_return"] = back
    data = base.model_dump()
    for key, value in update.items():
        # Dotted keys reach nested settings, e.g. "travel.car" = None (no car).
        *path, last = key.split(".")
        node = data
        for part in path:
            node = node[part]
        node[last] = value
    c = base.model_validate(data) if update else base
    back = c.last_return
    rules = c.stay_rules
    earliest = back + timedelta(days=rules.min_gap_days) if back else None
    latest = back + timedelta(days=rules.max_gap_days) if back else None
    best = shortlist(build_options(c, accommodation, transport, find_windows(c)), n=top)
    return Scenario(back, label, earliest, latest, best)


def parse_variant(text: str) -> tuple[str, dict[str, object]]:
    """'C: fly:solo_max_days=9,travel.car=none' -> label and field changes."""
    label, _, rest = text.rpartition(":")
    changes: dict[str, object] = {}
    for part in filter(None, (p.strip() for p in rest.split(","))):
        key, _, value = part.partition("=")
        low = value.strip().lower()
        if low in ("none", "null"):
            changes[key.strip()] = None
        elif low in ("true", "false"):
            changes[key.strip()] = low == "true"
        elif low.lstrip("-").isdigit():
            changes[key.strip()] = int(low)
        else:
            changes[key.strip()] = value.strip()
    return label.strip(), changes


# ---------------------------------------------------------------- view model


@dataclass
class Segment:
    kind: str  # pl, it, solo, uk
    left: float  # percent of the axis
    width: float
    title: str


@dataclass
class Marker:
    left: float
    icon: str
    title: str


@dataclass
class Row:
    who: str
    segments: list[Segment]
    markers: list[Marker]


@dataclass
class OptionView:
    key: str  # e.g. "2A"
    letter: str
    start: date
    end: date
    nights: int
    mode: str
    family_together: bool
    martin_hours: float | None  # None while a flight is still to check
    family_hours: float | None
    cost: float
    legs: list[dict[str, str]]
    pros: list[str]
    cons: list[str]
    rows: list[Row]
    open_checks: int  # flights, hire cars or trains not checked live yet
    family_text: str = ""
    recommended: bool = False


@dataclass
class Tick:
    left: float
    text: str
    major: bool


@dataclass
class Band:
    left: float
    width: float
    title: str


@dataclass
class ScenarioView:
    index: int
    title: str
    label: str
    back: date | None
    window_text: str
    options: list[OptionView]
    ticks: list[Tick] = field(default_factory=list)
    house_blocks: list[Band] = field(default_factory=list)
    fixed: list[Marker] = field(default_factory=list)
    window_band: Band | None = None
    best: OptionView | None = None


def _mode(o: Option) -> str:
    if o.martin_drives:
        return "Martin drives, Paula and Basia fly"
    if o.family_together:
        return "Everyone flies together"
    return "Everyone flies, separate days"


def _leg_text(leg: Leg) -> dict[str, str]:
    who = {"everyone": "Everyone", "Martin": "Martin", "family": "Paula + Basia"}[leg.who]
    if leg.mode == "car":
        what, status = f"Car Poznań to Faenza, about {leg.hours or 0:.0f} h", "car"
        if leg.direction == "return":
            what = f"Car Faenza to Poznań, about {leg.hours or 0:.0f} h"
    elif leg.choice is None:
        what, status = "Flight not checked yet", "open"
    else:
        f = leg.choice
        what = (
            f"{f.carrier} {f.origin} to {f.destination}, {f.depart:%H:%M}, "
            f"{leg.hours or 0:.1f} h door to door"
        )
        status = "checked" if f.checked_on else "unchecked"
    return {
        "day": f"{leg.day:%a %d %b}",
        "who": who,
        "direction": leg.direction,
        "what": what,
        "status": status,
    }


class _Axis:
    def __init__(self, start: date, end: date) -> None:
        self.start, self.days = start, max((end - start).days, 1)

    def pos(self, d: date) -> float:
        return round(100 * min(max((d - self.start).days, 0), self.days) / self.days, 3)

    def span(self, a: date, b: date) -> tuple[float, float]:
        left = self.pos(a)
        return left, round(self.pos(b) - left, 3)


def _person_row(
    axis: _Axis, who: str, away: tuple[date, date], solo: list[tuple[date, date]], o: Option
) -> Row:
    """One person's days: Poland, then Italy (some nights alone elsewhere), maybe UK."""
    end_axis = axis.start + timedelta(days=axis.days)
    start, end = away
    parts: list[tuple[str, date, date, str]] = [("pl", axis.start, start, "Poland")]
    italy = f"Italy ({o.house.name})"
    cursor = start
    for s, e in solo:
        if s > cursor:
            parts.append(("it", cursor, s, italy))
        place = o.solo_place.name if o.solo_place else o.house.name
        parts.append(("solo", s, e, f"Martin alone ({place})"))
        cursor = e
    parts.append(("it", cursor, end, italy))
    home = end
    onward = next((leg for leg in o.legs if leg.direction == "home"), None)
    if onward is not None:
        parts.append(("uk", end, onward.day, "Onward trip"))
        home = onward.day
    parts.append(("pl", home, end_axis, "Poland"))
    segments = []
    for kind, a, b, title in parts:
        if b <= a:
            continue
        left, width = axis.span(a, b)
        segments.append(Segment(kind, left, width, f"{title}: {a:%d %b} to {b:%d %b}"))
    markers = []
    mine = ("Martin", "everyone") if who == "Martin" else ("family", "everyone")
    for leg in o.legs:
        if leg.who not in mine:
            continue
        icon = "car" if leg.mode == "car" else "plane"
        t = _leg_text(leg)
        markers.append(Marker(axis.pos(leg.day), icon, f"{t['day']}: {t['what']}"))
    return Row(who, segments, markers)


def _ticks(axis: _Axis) -> list[Tick]:
    ticks = []
    for i in range(axis.days + 1):
        d = axis.start + timedelta(days=i)
        if d.day == 1:
            ticks.append(Tick(axis.pos(d), f"{d:%b}", True))
        elif d.weekday() == 0:
            ticks.append(Tick(axis.pos(d), f"{d.day}", False))
    return ticks


def _option_rank(o: Option) -> tuple:
    return (
        not o.family_together,
        not o.martin_drives,
        o.worst_tier,
        o.soft,
        o.travel_hours,
        o.total_cost_eur,
    )


def build_view(
    scenarios: list[Scenario], c: Constraints, accommodation: AccommodationFile
) -> list[ScenarioView]:
    house = next(a for a in accommodation.accommodation if a.preferred)
    views: list[ScenarioView] = []
    best_of: list[tuple[ScenarioView, Option]] = []
    for i, s in enumerate(scenarios, start=1):
        ends = [max([o.window.end, *(leg.day for leg in o.legs)]) for o in s.options] or [
            s.latest or c.horizon.end
        ]
        start = s.back or min(o.window.start for o in s.options) - timedelta(days=7)
        axis = _Axis(start, max(ends) + timedelta(days=4))
        title = f"Back in Poznań {s.back:%a %d %b}" if s.back else "Next stay"
        window_text = (
            f"Next stay can start {s.earliest:%a %d %b} to {s.latest:%a %d %b}"
            if s.earliest and s.latest
            else ""
        )
        view = ScenarioView(i, title, s.label, s.back, window_text, [], _ticks(axis))
        if s.earliest and s.latest:
            left, width = axis.span(s.earliest, s.latest + timedelta(days=1))
            view.window_band = Band(left, width, window_text)
        for r in house.unavailable:
            if r.end > axis.start and r.start < axis.start + timedelta(days=axis.days):
                left, width = axis.span(r.start, r.end)
                title_ = f"{house.name} not available {r.start:%d %b} to {r.end:%d %b}"
                view.house_blocks.append(Band(left, width, title_))
        for p in c.presence:
            if p.strength == "must" and p.where in ("PL", "UK") and axis.pos(p.start) < 100:
                if p.start >= axis.start:
                    who = ", ".join(p.who)
                    view.fixed.append(
                        Marker(axis.pos(p.start), "pin", f"{p.start:%d %b}: {p.title} ({who})")
                    )
        for letter, o in zip(LABELS, s.options, strict=False):
            w = o.window
            solo = [(w.start, o.house_start)] * (o.house_start > w.start)
            solo += [(o.house_end, w.end)] * (o.house_end < w.end)
            rows = [
                _person_row(axis, "Martin", (w.start, w.end), solo, o),
                _person_row(
                    axis,
                    "Paula + Basia",
                    (o.family_start or o.house_start, o.family_end or o.house_end),
                    [],
                    o,
                ),
            ]
            view.options.append(
                OptionView(
                    key=f"{i}{letter}",
                    letter=letter,
                    start=w.start,
                    end=w.end,
                    nights=w.days,
                    mode=_mode(o),
                    family_together=o.family_together,
                    martin_hours=None
                    if any(g.missing for g in o.legs if g.who in ("Martin", "everyone"))
                    else o.martin_hours,
                    family_hours=None
                    if any(g.missing for g in o.legs if g.who in ("family", "everyone"))
                    else o.family_hours,
                    cost=o.total_cost_eur,
                    legs=[_leg_text(leg) for leg in o.legs],
                    pros=o.pros,
                    # Open flights show in the journeys list instead.
                    # Prices are not shown yet, so unknown prices are left out too.
                    cons=[
                        x
                        for x in o.cons
                        if not x.startswith("No direct flight") and "price per night" not in x
                    ],
                    rows=rows,
                    # Flights not found yet or not checked live, plus hire cars or
                    # trains without a live price.
                    open_checks=o.open_ground
                    + sum(
                        leg.mode == "flight"
                        and (leg.choice is None or leg.choice.checked_on is None)
                        for leg in o.legs
                    ),
                    family_text=(
                        f"Paula and Basia at {o.house.name} "
                        f"{(o.family_start or o.house_start):%d %b} to "
                        f"{(o.family_end or o.house_end):%d %b}."
                    ),
                )
            )
        # Only options whose flights were all checked live can be proposed.
        checked = [
            (ov, o) for ov, o in zip(view.options, s.options, strict=False) if not ov.open_checks
        ]
        if checked:
            view.best = checked[0][0]
            best_of.append((view, checked[0][1]))
        elif view.options:
            view.best = view.options[0]
        views.append(view)
    # Recommend the scenario whose best checked option ranks best (timing first).
    if best_of:
        top = min(best_of, key=lambda vo: _option_rank(vo[1]))[0]
        if top.best:
            top.best.recommended = True
    return views


def render(
    scenarios: list[Scenario],
    c: Constraints,
    accommodation: AccommodationFile,
    generated: date | None = None,
) -> str:
    env = Environment(
        loader=PackageLoader("planner", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    views = build_view(scenarios, c, accommodation)
    recommended = next((o for v in views for o in v.options if o.recommended), None)
    rec_scenario = next((v for v in views if recommended in v.options), None)
    return env.get_template("report.html.j2").render(
        scenarios=views,
        recommended=recommended,
        rec_scenario=rec_scenario,
        house=next(a for a in accommodation.accommodation if a.preferred).name,
        generated=generated or date.today(),
    )


def write(html: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
