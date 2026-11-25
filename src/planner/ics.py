"""Import calendars from .ics files or Google Calendar's private iCal links.

This is the no-Claude version of the import-calendar skill: the same rules, applied by
plain code. Events it cannot classify (no Who tag, no location) are listed, not guessed.
"""

import re
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import icalendar
import recurring_ical_events

PEOPLE = {
    "martin": ["Martin"],
    "paula": ["Paula"],
    "basia": ["Basia"],
    "girls": ["Paula", "Basia"],
    "all": ["Martin", "Paula", "Basia"],
}
TAG = re.compile(r"#(\w+)")


@dataclass
class Event:
    calendar: str
    title: str
    text: str  # title + description + location, for tag search
    location: str
    start: date
    end: date  # last day, included
    description: str = ""

    @property
    def tags(self) -> set[str]:
        return {t.lower() for t in TAG.findall(f"{self.title} {self.description}")}


def load_ics(source: str) -> bytes:
    """A local path or an https:// iCal link (Google's 'secret address in iCal format')."""
    if source.startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=30) as resp:  # noqa: S310
            return resp.read()
    return Path(source).read_bytes()


def read_events(calendar: str, data: bytes, start: date, end: date) -> list[Event]:
    cal = icalendar.Calendar.from_ical(data)
    out = []
    for ev in recurring_ical_events.of(cal).between(start, end + timedelta(days=1)):
        s, e = ev.get("DTSTART").dt, ev.get("DTEND")
        e = e.dt if e is not None else s
        all_day = not isinstance(s, datetime)
        s_day = s.date() if isinstance(s, datetime) else s
        e_day = e.date() if isinstance(e, datetime) else e
        # All-day ends are exclusive in iCal; timed events are one day.
        last = e_day - timedelta(days=1) if all_day and e_day > s_day else s_day
        title, desc = str(ev.get("SUMMARY", "")), str(ev.get("DESCRIPTION", ""))
        loc = str(ev.get("LOCATION", ""))
        out.append(Event(calendar, title, f"{title}\n{desc}\n{loc}", loc, s_day, last, desc))
    return sorted(out, key=lambda x: x.start)


def _where(ev: Event) -> str | None:
    for tag, code in (("pl", "PL"), ("it", "IT"), ("uk", "UK"), ("any", "any")):
        if tag in ev.tags:
            return code
    loc = ev.location.lower()
    if re.search(r"poznań|poznan|\bpl\b|poland|polska", loc):
        return "PL"
    if re.search(r"italy|italia|faenza|bologna|\bit\b", loc):
        return "IT"
    return None


def _who(ev: Event) -> list[str] | None:
    names: list[str] = []
    for t in sorted(ev.tags):
        for p in PEOPLE.get(t, []):
            if p not in names:
                names.append(p)
    return names or None


def _r(ev: Event) -> dict:
    return {"start": ev.start, "end": ev.end}


def apply_events(c: dict, a: dict, events: list[Event]) -> list[str]:
    """Replace the calendar-derived parts of constraints `c` and accommodation `a`.

    Returns the lines that need Martin's attention (nothing is guessed).
    """
    todo: list[str] = []
    for key in ("office_required", "other_travel", "presence", "holidays", "shutdown", "leave"):
        c[key] = []
    blocks: list[dict] = []
    trips: list[Event] = []
    for ev in events:
        title, tags = ev.title.strip(), ev.tags
        if ev.calendar == "Holidays in Poland":
            if "public holiday" in ev.description.lower():
                for i in range((ev.end - ev.start).days + 1):
                    c["holidays"].append(
                        {"day": ev.start + timedelta(days=i), "country": "PL", "name": title}
                    )
        elif ev.calendar == "Travel":
            if "non disponibile" in title.lower():
                blocks.append({"start": ev.start, "end": ev.end + timedelta(days=1)})
            elif title.lower().startswith(("flight", "stay", "train")):
                trips.append(ev)
        elif ev.calendar == "Work":
            low = title.lower()
            if low.startswith("public holiday"):
                for i in range((ev.end - ev.start).days + 1):
                    c["holidays"].append({"day": ev.start + timedelta(days=i), "country": "IT"})
            elif "shutdown" in tags:
                c["shutdown"].append(_r(ev))
            elif "holiday" in tags:
                c["leave"].append(_r(ev))
            elif low in ("faenza", "uk"):
                c["other_travel"].append(_r(ev))
            elif "it" in tags and "martin" in tags:
                c["office_required"].append(_r(ev))
            else:
                _presence(c, todo, ev, only_tagged=True)
        elif ev.calendar in ("Family", "Important"):
            _presence(c, todo, ev, only_tagged=False)
    return _finish(c, a, trips, blocks, todo)


def _presence(c: dict, todo: list[str], ev: Event, only_tagged: bool) -> None:
    tags = ev.tags
    if only_tagged and not tags & {"pl", "it", "uk"}:
        return
    if tags & {"flex", "any"}:
        return
    where, who = _where(ev), _who(ev)
    if where is None or who is None:
        missing = "where" if where is None else "who"
        todo.append(f"{ev.start} {ev.calendar}: {ev.title} (missing {missing} tag)")
        return
    c["presence"].append(
        {
            "title": ev.title.strip(),
            **_r(ev),
            "where": where,
            "who": who,
            "strength": "pref" if "pref" in tags else "must",
        }
    )


def _finish(c: dict, a: dict, trips: list[Event], blocks: list[dict], todo: list[str]) -> list[str]:
    # Group flights into trips: events within one day of each other merge.
    merged: list[dict] = []
    for ev in sorted(trips, key=lambda x: x.start):
        if merged and ev.start <= merged[-1]["end"] + timedelta(days=1):
            merged[-1]["end"] = max(merged[-1]["end"], ev.end)
        else:
            merged.append(_r(ev))
    c["other_travel"].extend(merged)
    if merged:
        c["last_return"] = merged[-1]["end"]
        todo.append(f"last_return set to {merged[-1]['end']}: check it is the day you land in PL")
    for acc in a.get("accommodation", []):
        if acc.get("preferred") and not acc.get("available"):
            acc["unavailable"] = blocks
    return todo
