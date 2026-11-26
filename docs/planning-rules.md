# Planning rules and steps

One page with every rule Martin has set, and the fastest way to plan a stay.
Where a rule lives in the code or data, the setting is named in `code`.
Real values (home address, prices) live in the gitignored `data/` files.

## Rules

### Where and when
- **La Suite Elena (Faenza)** is the family's place. The family only goes to Italy
  when it is free. Martin may stay alone somewhere else for up to 7 nights
  (`solo_max_days`).
- **City break**: if La Suite isn't free yet, Paula and Basia may arrive up to
  3 nights early on a day off and stay somewhere else first
  (`family_flights.bridge_nights`). That stay is priced from a live quote
  (`quotes:` in accommodation.yaml).
- **Office days**: Martin never travels to Italy on a required office day. He
  arrives the day before at the latest (`stay_rules.travel_on_office_days`).
- **Hourly pay**: every hour off costs money. The car only travels on days off
  (weekends, public holidays, shutdown, leave) (`car.days_off_only`).
- **Soft rules**: these only change the ranking.
  - Avoid flying on Polish or Italian long weekends, because prices are higher.
  - Be in Poland on public holidays.

### Holidays (Martin, 25 Nov 2026)
- **Days off that cost nothing**: weekends, Italian public holidays (the office is
  closed) and shutdowns. Polish public holidays are normal paid working days for
  Martin, so a day off on one costs pay like any other.
- **Plan holidays around shutdowns and Italian holidays**, so that as few paid
  days as possible are lost.
- **Each year**:
  - One long holiday of about 4 weeks, built around the summer shutdown.
  - One 2-week holiday.
  - Long weekends wherever an Italian holiday makes one cheap (bridge days).
  - The winter shutdown is usually busy: add at most 1 to 2 extra days to it.
- **Avoid peak prices** where possible: school-holiday peaks and long weekends.
- **Where**: not part of the plan yet.
- **How the planner picks them** (`planner year`, settings under `year_plan`):
  - A holiday is a run of days off that starts right after a working day and ends
    right before one, so no free day next to it is wasted. Its cost is the paid
    days inside it.
  - Ranking: fewest paid days, then the most days off for them, then the fewest
    school-holiday days (`year_plan.peaks`, from the official school calendars).
  - Long holiday: 28 to 31 days that contain the whole summer shutdown.
  - Two-week holiday: 14 to 17 days, at least 6 weeks from the long one, not on
    an office period, a decided stay or a shutdown. Martin prefers it in March or
    April (`second_holiday_months`); for 2027 around Basia's birthday
    (`second_holiday_start`).
  - Long weekends: for each Italian holiday on a weekday, the free version and
    the versions with 1 or 2 bridge days.
  - Christmas: the shutdown plus at most 2 paid days.

### Year plan (draft rhythm)
- **Remote work 55 to 65% of working days** (Martin, 25 Nov 2026): the rest is
  office time in Faenza. Working days leave out weekends, Italian holidays,
  shutdowns and his holidays (`year_plan.remote_share`).
- Stays in Faenza of 14 to 21 nights, with 28 to 42 nights in Poznań between
  them by default. The planner also tries other stay and gap lengths and keeps
  the one with the remote share in range and the **fewest trips**: Martin prefers
  fewer, longer stays (3 to 4 weeks) over many 2-week ones. Holidays don't count as
  Poznań time.
- Later: workations (remote work from the family home or elsewhere) outside the
  Faenza stays. Martin will give the rules for family visits.
- Every stay starts and ends on a day off, so Martin can drive or fly without
  losing pay. No stay touches a holiday, a shutdown or a day he must be in Poland.
- Required office periods lie fully inside a stay. Decided stays are fixed
  (`year_plan.fixed_stays`).
- La Suite blocked for more than 7 nights of a stay rules it out. Fewer blocked
  nights, Polish holidays away from home and travel on long weekends or in
  school holidays all count against a stay.
- It is a rhythm, not a booking plan. Each stay is planned with live checks a few
  weeks ahead (steps below).

### Travel
- **Timing first, cost second.** For longer stays Martin drives (about 13 h) and
  Paula and Basia fly. They never all drive together.
- **Direct flights only**, in this route order (`route_tiers`):
  1. Poznań to Bologna, Rimini or Forlì.
  2. Poznań to another nearby Italian airport.
  3. Wrocław, Warsaw Chopin or Berlin to Bologna. Never Modlin.
  4. Otherwise, ask Martin.
- **Paula and Basia's comfort comes first.**
  - Hard limits: they leave home (Poznań or Faenza) at 05:00 or later and
    arrive home by 20:00 (`family_flights.leave_home_after` /
    `arrive_home_by`).
  - Then, in order: a weekend flight, the shortest door-to-door time, a
    departure between 10:00 and 18:00, and the route tier.
  - Their arrival may move up to 4 days into the stay
    (`family_flights.shift_days`). Martin prefers it does not move.
- **Getting to Polish airports.**
  - Poznań: taxi (Bolt/Uber, about 60 zł).
  - Paula and Basia to Wrocław or Warsaw: a relative drives them
    (`family_lifts`). Martin pays the relative's fuel and tolls, there and back.
  - Martin alone to a far airport: a live-checked bus or train. Paula can't
    drive him, and he never sleeps at the airport.
- **In Italy.**
  - With Paula and Basia, a car is always needed: Martin's own car or a hire car.
  - Martin alone, flying into Bologna, takes the Marconi Express and a train if
    one fits with time to spare. Otherwise he hires a car.
  - A hire-car quote must match the pick-up and drop-off airports
    (`pick_up` / `drop_off`).
- **Time margins**: at least 1.5 h at the airport before take-off, and 0.5 h
  after landing.
- **Luggage and infant.**
  - Basia flies on Paula's lap, with an infant fee per flight.
  - When Martin drives, the big bags go in the car and Paula and Basia take hand
    luggage only.
  - Otherwise, count one 20 kg bag per adult per flight.

### Data and prices
- **Live data only.** Never use a guessed price.
  - Flights: from the airline's own site. Momondo only to discover routes.
  - Hire cars: Kayak. Trains: Trenitalia. Buses: FlixBus. Stays: Booking or
    Airbnb.
  - Tolls: calcolopedaggio.it (Italy) and autostrada-a2.pl (A2 in Poland).
  - Fuel: EU Oil Bulletin.
  - Every price keeps its source and check date.
- **Never propose an option with an unchecked leg.** The report marks such an
  option "not a proposal yet".
- **Summary per option**: door-to-door time for each journey, and the total cost
  by kind.
  - Kinds: flights, infant fees, bags, car hire, own car, tolls and fuel, taxis,
    relatives' lifts, trains and buses, accommodation.
  - Door to door ends at Faenza on a weekend or evening arrival, or at the
    office on a weekday arrival straight to work.
- **Never book, buy or confirm anything.** Calendar events are added only after
  Martin approves a plan.

## Steps (fastest path)

1. **Calendar**: run the `import-calendar` skill. This only needs doing when the
   calendars have changed.
   - Once a year (or when holidays or La Suite dates change), run
     `uv run planner year --out out/year.html` for the yearly rhythm and holiday
     proposals. Then plan each stay from step 2.
2. **Dates**: `uv run planner report --back DATE ...` shows the windows, options
   and which legs are still open.
3. **Time limits**: `uv run planner routes --month YYYY-MM` lists, per route,
   which departure and landing times can work, plus a Ryanair link per route
   that shows a whole month at once. Routes outside those times never need
   checking.
4. **Flights**: run `uv run planner fares --month YYYY-MM` for Ryanair candidates,
   then the `find-flights` skill for the rest.
   - Open one Ryanair month page per route and keep the days that fall inside the
     time window.
   - Confirm only the finalists on the normal Ryanair booking page.
   - Use Momondo only for other airlines.
5. **Ground and stays**: check the hire car on Kayak for the exact airports,
   trains on Trenitalia, buses on FlixBus, and stays on Booking, only for the
   finalists. Record each one under `ground:` or `quotes:`.
6. **Re-run the report**, republish the page, and give Martin the result and
   the open questions.
