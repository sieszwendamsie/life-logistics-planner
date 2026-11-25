---
name: plan-year
description: Draft a whole-year plan - holidays around shutdowns and Italian public holidays, and a rhythm of Faenza stays with the right remote/office share. Use when Martin asks for a year plan, holiday proposal, or "when should I take leave".
---

# Plan the year

Goal: a proposed year (holidays plus Faenza stays) that Martin can approve or
adjust, built on `docs/planning-rules.md`. Read its "Holidays" section first.

Key rules (Martin, Nov 2026):
- Martin is a paid-by-the-hour contractor: every working hour off is lost pay.
  Weekends, Italian public holidays and shutdowns cost nothing. Polish public
  holidays are normal working days for him.
- Each year: one long holiday of about 4 weeks around the summer shutdown, one
  2-week holiday (March or April preferred), long weekends from Italian holiday
  bridges, and at most 1 to 2 extra days on the busy winter shutdown.
- Remote work should be about 55 to 65 percent of working days
  (`year_plan.remote_share`). Prefer fewer, longer stays.
- Avoid school-holiday peaks and pricey long weekends where possible.
- Where to holiday is not part of the plan yet. Do not invent destinations.
- Never book or confirm anything. Add to the calendar only after approval.

## Steps

1. **Fresh data.** Run `import-calendar` if the calendars changed. Check that the
   Work calendar has the year's Italian public holidays and shutdowns. If a
   holiday is missing, tell Martin; do not guess it.
2. **Run the year planner.** `uv run planner year --help` shows its options
   (it ships with the year-plan work; if the command is missing in this checkout,
   say so and stop rather than doing the arithmetic by hand). Pin Martin's own
   choices with `long_holiday_start` and `second_holiday_start` in
   `data/constraints.yaml`.
3. **Check against family and school dates.** Family calendar events
   (for example birthdays, Easter) are `#pref` or `#must`; school holiday peaks
   must be verified on the school authority's own site, with the date. Say which
   dates could not be verified.
4. **Present.** Holidays with days off and paid days lost, each stay with dates
   and the resulting remote share, clashes and open questions. Publish the page
   as an Artifact and ask Martin to approve or change.
5. **After approval only:** write the plan to the `Proposed schedule` calendar,
   then report exactly what was added. For flights of any stay, continue with
   the `plan-next-stay` skill.
