---
name: plan-next-stay
description: Plan Martin's next stay between Poznań and Italy end to end - import calendars, find windows, build options, check live flights, and present a report to approve. Use when he asks "plan the next stay", "when can we go", or names a return date to compare.
---

# Plan the next stay

This is the main workflow. It chains the other skills and the `planner` commands.
Read `docs/planning-rules.md` first: it holds every rule and is the source of truth.

Hard rules (details in CLAUDE.md and the rules doc):
- Never book, buy or confirm anything. Prepare proposals only.
- Prices and flight times only from live checks with a source and check date.
  Never guess. Never propose an option with an unchecked leg.
- Add events to Google Calendar only after Martin approves a plan.
- `data/` and `out/` hold real personal data: never commit them.

## Steps

1. **Calendars.** If `data/constraints.yaml` is missing, or Martin says the
   calendars changed, run the `import-calendar` skill. Otherwise skip it and say
   when the data was last imported.
2. **Windows.** `uv run planner windows --limit 5` lists feasible stay dates.
   If Martin gave return dates, use them as `--back DATE[=LABEL]` scenarios.
   Otherwise take the top windows. Ask only when something is truly unclear
   (for example an untagged calendar event: ask who is required).
3. **Options and open legs.** `uv run planner report --back ...` writes
   `out/report.html` and shows which journeys still say "Flight not checked yet".
   Add `--variant "LABEL:solo_max_days=9"` to test a changed rule.
4. **Time limits.** `uv run planner routes --month YYYY-MM` prints which flight
   times can work per route. Skip anything outside those times.
5. **Flights.** Run the `find-flights` skill for the open journeys. Check the
   recommended option first and no more than about 10 journeys without asking.
6. **Ground and stays.** For the finalists only: hire car (Kayak), trains
   (Trenitalia), buses (FlixBus), stays (Booking or Airbnb), tolls. Record each
   under `ground:` or `quotes:` as the find-flights skill describes.
7. **Re-run the report** and publish `out/report.html` to the same Artifact page.
8. **Hand over.** Tell Martin in a few lines: the recommended option, its total
   door-to-door time and cost, what is still open, and the check dates. Ask him
   to approve, change or reject. Do nothing in the calendar until he approves.
9. **After approval only:** add the plan to the `Proposed schedule` calendar with
   the Google Calendar tools, then tell him exactly what was added.

## Output to give Martin

Per option: dates, who travels how, every flight in full (airline, flight number,
route, times, price, source, check date), total door-to-door time, total cost by
kind. A short recommendation with the reason. The open questions at the end.
