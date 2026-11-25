---
name: import-calendar
description: Read Martin's Google Calendars (Travel, Family, Important, Work) and fill the planner's real data files in data/. Use before planning a stay, or when he says the calendars changed.
---

# Import the calendars into data/

Goal: turn calendar events into `data/constraints.yaml` and `data/accommodation.yaml`
so `uv run planner windows` and `uv run planner options` work on real dates.
This skill only reads calendars. Never create, change or delete calendar events here.
`data/` is gitignored: never commit it, and never copy real event details into
committed files.

## 1. Prepare the data files

- If `data/constraints.yaml` does not exist, copy `examples/constraints.yaml` and
  empty the example dates: `office_required`, `poznan_required`, `family`,
  `other_travel`, `presence`, and comment out `onward`. Keep `stay_rules`, `travel`
  and `solo_max_days`.
- If `data/accommodation.yaml` does not exist, copy the example, rename the
  preferred place to `La Suite Elena` (`location: Faenza`), remove its `available`
  list, and keep one alternative. Ask Martin for real alternatives later.
- If `data/options.yaml` does not exist, create it with `options: []`.
- If a file exists, update only the fields below and keep everything else.

## 2. Find the calendars

Call `list_calendars` and pick by name: **Travel**, **Family**, **Important**,
**Work**. If one is missing (Work may not exist yet), say so and continue.
Skip "Proposed schedule" (planner output) and "Holidays in Poland".

Planning horizon: `horizon` in constraints, or today to six months from today.
Read each calendar with `list_events`, ordered by start time.

## 3. Travel calendar (no tags needed)

| Event title | What to write |
|---|---|
| `La Suite - non disponibile` | `unavailable` range on La Suite: `start` = first day, `end` = the all-day end date (Google's end is already the check-out day) |
| `La Suite Faenza - Elena` | Our own booking. Not a block; nothing to write |
| `Flight: XX 1234 from AAA to BBB` | A booked journey (see below) |
| Trains, `Stay: ...` hotels | Part of a booked trip; use only to find trip start and end |

Booked trips:
- Group flights and trains into trips. A trip starts when someone leaves Poland
  and ends when they land back in Poland.
- Add each booked trip, from its first to its last day, to `other_travel` (this
  keeps the car away from it).
- Set `last_return` to the day the latest booked trip lands back in Poland.
- If a trip leaves Italy for a third country (for example `BLQ to LTN`) and there
  is no flight back to Poland, stop and ask Martin where and when they fly home.
  Do not guess `last_return`.

## 4. Family, Important and Work calendars (tags)

Read tags from the event description (and title, if Martin put them there):

- **Where:** `#PL` `#IT` `#UK` `#any`
- **Who:** `#Martin` `#Paula` `#Basia` `#girls` `#all` (`#girls` = Paula and Basia,
  `#all` = all three)
- **How fixed:** `#must` (default) `#pref` `#flex`

Rules:
- Tags are not case-sensitive: `#paula` is the same as `#Paula`.
- **Where, untagged:** use the Location field (an address in Poznań = `PL`, in
  Italy = `IT`). With no tag and no location, ask.
- **Who, untagged:** always ask Martin. Do not assume. Ask in one message,
  listing each event as date, calendar and title, with a suggested answer where
  the title hints at it ("Okulista Basia" suggests Basia). Write nothing for those
  events until he answers. Suggest he adds the tags in the calendar so the
  question does not come back.
- **Dates:** timed events are one day (`start` = `end` = the event's date).
  All-day events: `end` = the all-day end date minus one day (presence dates
  include both ends).
- Skip `#flex` and `#any` events: they never limit planning.
- Write each event as a `presence` entry:

```yaml
presence:
  - {title: Logopeda, start: 2027-01-13, end: 2027-01-13, where: PL, who: [Basia], strength: must}
```

Office days in Italy come from the Work calendar as `#IT #Martin` events.

## 5. Check and report

1. Run `uv run planner windows --constraints data/constraints.yaml --limit 5`.
   If loading fails, fix the YAML and run it again.
2. Tell Martin in a few lines: how many events were read per calendar, how many
   La Suite blocks, the `last_return` date, how many windows were found, and the
   questions that still need his answer.
