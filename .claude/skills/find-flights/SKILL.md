---
name: find-flights
description: Check live direct flights (Ryanair, Wizz, Momondo) for the open journeys of the planner's options and record them in data/options.yaml. Use after planner report shows "Flight not checked yet", or when Martin asks for flights for a stay.
---

# Find flights for the open journeys

Goal: replace every "Flight not checked yet" in the report with a real, live flight,
so the options can be compared on real times. Read only: never book, never log in,
never enter personal or payment details, never click "Continue" past the flight list.

## Rules (from Martin)

- **Live data only, airline site first.** Every flight's time and price comes from
  the airline's own site (Ryanair, Wizz, Eurowings, LOT...), checked now. Momondo is
  for discovery only: finding which airlines fly a route on a day, and spotting a
  cheaper fare. If Momondo shows a cheaper price, keep it as a note and still confirm
  the flight on the airline site. Never from schedule sites (FlightMapper and similar were
  wrong before). If a page does not load after two tries, say so and leave the
  journey open. Never guess.
- **Direct flights only**, in the route order of `travel.route_tiers` in
  `data/constraints.yaml`: tier 1 first (POZ to BLQ/RMI/FRL), then tier 2 (POZ to
  another nearby Italian airport), then tier 3 (WRO, WAW Chopin, BER to BLQ; never
  Modlin). Stop at the first tier that has a flight on the day. Return journeys use
  the same routes reversed. If no tier has one, say "ask for an alternative route".
- When Martin drives, he has no flight, but Paula and Basia still fly: check theirs.
- 3-way trips (`onward` set): also check Italy to the UK (`onward` journey) and the
  UK to Poznań (`home` journey); UK airports Luton and Stansted.

## 1. Know what to check

Run the report for the scenarios being discussed:

```
uv run planner scenarios --back DATE[=LABEL] ...
```

Each "no direct flight on your routes yet" line is an open journey: who, direction
and day. Check the recommended option first, then the others. Do not check more
than about 10 journeys in one go; ask Martin before doing more.

## 2. Search in the browser

Use the Claude in Chrome tools (Martin's own Chrome, with his OK). Open a new tab,
and close it when done. Decline non-essential cookies.

- Ryanair, prices in EUR, one way, one adult:
  `https://www.ryanair.com/ie/en/trip/flights/select?adults=1&teens=0&children=0&infants=0&dateOut=YYYY-MM-DD&isReturn=false&originIata=XXX&destinationIata=YYY`
- Wizz Air: `https://wizzair.com/en-gb/booking/select-flight/XXX/YYY/YYYY-MM-DD/null/1/0/0/null`
- Momondo to see other airlines on the route, direct only:
  `https://www.momondo.com/flight-search/XXX-YYY/YYYY-MM-DD?sort=bestflight_a&fs=stops=0`

Momondo does not always list Ryanair. For every route, also open the Ryanair page
directly (Poznań, Wrocław, Warsaw Chopin and Berlin to the Italian airports and
back), even when Momondo shows nothing. Each Ryanair page shows five days around
the date: note which days have flights.

Read the page text. Note for each direct flight: flight number, departure and
arrival time (local), the basic fare per person, and seats-left warnings.

## 3. Record in data/options.yaml

One entry per flight found, with the price for everyone on the journey
(per person × 2 for Paula and Basia, × 3 for everyone, × 1 for Martin):

```yaml
- {id: ret-0302-bgy-poz, direction: return, carrier: Ryanair, origin: BGY,
   destination: POZ, depart: 2027-03-02T09:15:00, arrive: 2027-03-02T11:30:00,
   price_eur: 88.0, source_url: <the search page>, checked_on: 2026-11-25}
```

If the site shows another currency, write the converted EUR amount and add a
comment with the original. Keep earlier entries; update one if its time or price
changed. `data/` is gitignored: never commit it.

## 4. Re-plan and report

```
uv run planner report --back ...   # same scenarios as before
```

Republish `out/report.html` to the same Artifact page, then tell Martin in a few
lines: which journeys now have flights, which are still open and why, and whether
the recommendation changed. Mention seats-left warnings and the check date.
