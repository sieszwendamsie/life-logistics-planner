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
   Paula and Basia: their trips are planned for their convenience. Hard rule:
   leave home (Poznań or Faenza) no earlier than 05:00 and arrive home by
   20:00, door to door, or the flight is not used. A relative drives them to
   and from Poznań, Wrocław or Warsaw airports (`travel.family_lifts`, Google
   Maps time), so they need no bus or train. Then weekend flights first, the
   shortest door-to-door time, a departure between 10:00 and 18:00, and route
   choice. Their flight day may move up to 4 days into the stay to get one.
   When the house is not free yet, they may instead come up to 3 nights
   early on a day off (weekend or holiday) for a short city break elsewhere
   (`family_flights.bridge_nights`), priced from a live quote under the
   other place's `quotes:` in accommodation.yaml (Booking, Airbnb).
   Hire-car quotes record `pick_up` and `drop_off` airports and are only used
   when they match the flights. Avoid flying on long
   weekends in Poland or Italy (dearer), and prefer being in Poland on public
   holidays. These are soft rules: cons in the report, ranked after timing.
   Car: only on days Martin does not work (weekends, public holidays,
   shutdown, leave), because he is paid per hour. For long stays with no other travel plans nearby, Martin drives
   Poznań to Faenza and Paula and Basia fly. This is preferred when allowed.
   Driving cost is in the total (`travel.car.costs`, assumptions checked
   2026-11-25): 1400 km each way at 6 l/100 km, diesel €2.00/l (EU Oil Bulletin,
   9 Nov 2026: PL 1.75, CZ 1.90, AT 2.09, IT 2.22); Italian toll €32.20 one way
   (calcolopedaggio.it: Ugovizza-Tarvisio to Venezia Est €18.90, free Mestre
   bypass, Padova Est to Faenza €13.30; the full route via the Passante is
   €34.80); vignettes CZ 1/10/30 days €9.41/12.28/19.65 (230/300/480 Kč),
   AT 1/10 days and 2 months €9.80/13.00/32.60 (2-month bought online starts
   18 days later). Per country the cheaper of one vignette per drive or one
   long one covering both drives is used. When Martin flies there is no assumed
   price: hire cars (Kayak) and trains (Trenitalia, Marconi Express) are
   recorded live under `ground:` in options.yaml with source and check date.
   Paula and Basia always need a car. Martin alone takes the train when he
   flies into `travel.train_airports` (Bologna), else hires a car. An option
   with an unchecked hire car or train is not a proposal yet.
   Travel days: Martin never flies in on a required office day; he arrives
   the day before at the latest (`stay_rules.travel_on_office_days: false`).
   Airports other than `travel.home_airports` (Poznań) need a live-checked
   bus or train from home (`ground:` kind transfer, per person), leaving home
   after `leave_home_after` (05:00) and arriving `airport_margin_hours` (1.5 h)
   before take-off. Paula can't drive him and he does not sleep at airports.
   Door-to-door time then counts from that bus or train.
   Door to door and cost summary: each option lists every journey from home
   to Faenza (or straight to the office when arriving on a working day by
   `office_if_arriving_by`) with leave and arrive times: taxi to Poznań
   airport (`travel.home_rides`, Bolt/Uber ~60 PLN), 1.5 h at the airport,
   the flight, 30 min after landing, then the drive (`travel.italy_drives`,
   Google Maps time, toll) or train. Cost is split into flights, car hire,
   own car, driving in Italy (tolls + fuel, also for hire cars: two drives
   when Martin fetches Paula and Basia), taxis, trains and buses.
   Seats: Martin and Paula; Basia flies on Paula's lap and pays the airline's
   infant fee per flight (`travel.infant_fee_eur`, Ryanair €25). When Martin
   drives, the large luggage goes in the car and Paula and Basia travel light
   (hand luggage + baby allowance). When nobody drives, each adult checks
   `checked_bags_per_adult` 20 kg bags per flight (`checked_bag_eur`; Ryanair's
   fee table maximum €59.99, since the exact price shows only while booking).
   An airline without a known fee leaves the option "not a proposal yet".
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
6. **HTML report.** Done: `planner report` writes `out/report.html`: comparison table,
   PL/IT timeline, recommendation, and the scenarios side by side
   (`--back`). Claude publishes it as a private page after each re-plan. Map links later.
7. **Transport research skill.** Done: `.claude/skills/find-flights/`. A skill that searches flight and transfer options
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

13. **Holidays and Work calendar.** Done: `holidays` (PL and IT), `shutdown`
    and `leave` in `constraints.yaml`, imported from the Work calendar and
    Holidays in Poland; long weekends, family flight preferences.
14. **Holiday proposals.** The planner proposes leave dates from La Suite
    availability and PL/IT public holidays. Rules to agree with Martin first.

Done when: Martin plans one real stay with it in about 15 minutes of review.
