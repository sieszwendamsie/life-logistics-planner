# Spec: MVP of the life logistics planner

This file turns [mvp.md](mvp.md) (the *what* and *why*) into the *how*: the stack,
the data, the workflow and a task list. If the two disagree on scope, mvp.md wins;
if they disagree on implementation, this file wins.

## 1. Approach: Claude Code is the app

For the MVP we do **not** build a web app. Claude Code already gives us a chat
interface, Google Calendar and Drive connectors (MCP), web search and a browser.
What is missing is small and specific:

1. A place to write down constraints and candidate options in a structured way.
2. Reliable date and cost maths (code is better than an LLM at this).
3. A clear visual comparison of 2–4 options.
4. A repeatable workflow that runs the same way every time.

So the MVP is: **plain data files + a small Python package + one HTML report +
Claude Code skills** that tie them to the connectors.

A web app (or a more autonomous agent) comes after the MVP proves the 15-minute
review loop works.

## 2. Stack

| Need | Choice | Why |
|---|---|---|
| Conversation, orchestration | Claude Code (skills in `.claude/skills/`) | Already have it; a skill is a saved, reusable workflow |
| Calendar read/write | Google Calendar MCP connector | Already connected; no custom OAuth code |
| Flights, stays, transport | Web search + browser, recorded into a file | No reliable free flight API for Ryanair/Wizz; MVP only needs a few options |
| Maps, travel time | Google Maps links (and later the Maps MCP if needed) | Zero setup |
| Data | YAML files validated by Pydantic | Human-readable, editable by hand or by Claude |
| Logic | Python 3.12, managed by `uv` | Readable for a beginner; `uv` is the fastest standard tool |
| Report | One static HTML file from a Jinja2 template | Opens in any browser; no server |
| Quality | `pytest`, `ruff` | Standard, zero-config |

## 3. Data

Personal data stays **out of git**. Real files live in `data/` (gitignored).
`examples/` holds fake data with the same shape, used by tests and as a template.

- `constraints.yaml`: stay rules (stay 21–28 days; gap between trips at least
  14 days, usually 4–5 weeks, at most 35), last return
  date, required/preferred office days in Italy, dates Martin must be in Poznań,
  family dates (together or separately).
- `accommodation.yaml`: preferred apartment availability (from the host, or a
  dedicated "host availability" calendar), plus alternatives with price per night.
- `options.yaml`: candidate transport legs collected during planning (carrier,
  route, date, times, price, source link, door-to-door time).

## 4. Workflow (the `/plan-next-stay` skill)

1. **Read constraints.** Pull events from Google Calendar for the planning
   horizon and update `data/constraints.yaml`. Ask Martin about anything unclear.
2. **Generate date windows.** `planner windows` lists feasible stay windows
   that satisfy the stay rules and hard constraints.
3. **Check accommodation** for each window. Always prefer the family house
   (La Suite Elena, Faenza): the family only travels when it is free. If it is
   not free, plan around it; Martin may stay alone in another place for at most
   `solo_max_days` (default 7).
4. **Collect transport options** for the best 3–5 windows (Momondo, Ryanair,
   Wizz, others) into `data/options.yaml`. Read only. Never book.
   Flight times and prices come only from a live search on the airline's own
   site or app, or Momondo, with `source_url` and `checked_on` filled in.
   Never use schedule or route sites (FlightMapper, FlightConnections and
   similar) for times: they can be out of date. If a live check is not possible,
   say so and ask Martin to paste what he sees.
   Direct flights only, searched in this order (`travel.route_tiers`):
   1. Poznań to Bologna, Rimini or Forlì.
   2. Poznań to another nearby Italian airport (Treviso, Venice, Verona,
      Bergamo, Florence, ...).
   3. Wrocław, Warsaw Chopin or Berlin (not Modlin) to Bologna.
   4. If none of these exist, ask Claude for an alternative route.
   Car: for long stays with no other travel plans nearby, Martin drives
   Poznań to Faenza and Paula and Basia fly. This is preferred when allowed.
5. **Compare.** `planner report` combines windows, stays and transport into
   2–4 options ranked by timing first (route choice, door-to-door time per
   person), cost last, with pros/cons and a recommendation,
   and writes `out/report.html` (timeline PL/IT, comparison table, map links).
6. **Scenarios.** Before Martin picks a flight or date, `planner scenarios`
   shows what each choice means for the next stay, side by side. Example:
   `--back 2027-01-02="FR 2194" --back 2027-01-06="FR 1750"` lists the best
   next-stay options for each possible day back in Poznań.
7. **Iterate.** Martin says e.g. "two more days in Poznań"; Claude updates the
   data and re-runs steps 2–5.
8. **Approve.** Only after Martin explicitly picks an option, Claude adds the
   events to Google Calendar and lists the bookings Martin should make himself.

## 5. Out of scope for the MVP

Booking or paying, reading the main Gmail, automatic price tracking, a hosted web
app, multi-user use.

## 6. Tasks

Each task is one small branch and pull request, in this order.

1. **Skeleton.** `pyproject.toml` with `uv`, `planner/` package, `pytest` and
   `ruff` set up, `data/` gitignored, a `planner --help` command.
2. **Data model.** Pydantic models and loaders for the three YAML files, with
   fake data in `examples/` and tests.
3. **Date windows.** `planner windows`: generate and filter stay windows from
   the rules and hard constraints. Tests with edge cases (month ends, overlaps).
4. **Calendar import skill.** Done: `.claude/skills/import-calendar/`. Reads the
   Travel, Family, Important and Work calendars through the MCP connector and
   writes `data/constraints.yaml` and `data/accommodation.yaml`. No Python.
5. **Option builder.** Combine windows, accommodation and transport into options
   with total cost, travel time and pros/cons. Tests.
6. **HTML report.** `planner report` writes `out/report.html`: comparison table,
   PL/IT timeline, map links, recommendation.
7. **Transport research skill.** A skill that searches flight and transfer options
   in the browser and records them in `data/options.yaml`.
8. **`/plan-next-stay` skill.** Ties steps 1–6 together, including the
   "change a requirement and recalculate" loop.
9. **Approve to calendar.** Add the chosen plan to Google Calendar after explicit
   approval only.
10. **Safety hook.** A hook that blocks committing files from `data/` or `out/`.
11. **3-way trips.** Done: `onward` in `constraints.yaml`. A stay can end with
    everyone flying on to a third country (for example Italy to the UK) and home
    from there after a set number of nights. The car is never used then.
    Example: fly Warsaw to Bologna, then Italy to the UK to visit family, then
    the UK straight back to Poznań. Later: plan the onward trip's dates too.
12. **Presence from the calendar.** Done: `presence` in `constraints.yaml`, one
    entry per event (`where` PL/IT/UK/any, `who` Martin/Paula/Basia, `strength`
    must/pref/flex). Martin's #PL/#UK must days block a stay, his #IT must days
    act like office days, Paula's or Basia's #PL/#UK must days shorten the
    family's part of the stay, and #pref days show up as cons.

Done when: Martin plans one real stay with it in about 15 minutes of review.
