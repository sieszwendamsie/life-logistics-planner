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
