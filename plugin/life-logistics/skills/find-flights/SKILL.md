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
- **Public transport only from real timetables**: getting to a far airport (FlixBus,
  PKP Intercity, DB) and trains in Italy (Trenitalia, Marconi Express) are checked
  live for the exact day and recorded under `ground:` with depart/arrive times,
  price, source and check date. Arrive at the airport at least 1.5 h before
  take-off; count 0.5 h after landing. No airport hotels, no lifts from Paula.
- 3-way trips (`onward` set): also check Italy to the UK (`onward` journey) and the
  UK to Poznań (`home` journey); UK airports Luton and Stansted.

All rules in one place: `docs/planning-rules.md`.

## 1. Know what to check

First get the time limits per route (Paula and Basia's 05:00-20:00 door to door,
Martin's earliest departure), with one Ryanair month link per route:

```
uv run planner routes --month YYYY-MM
```

Only flights inside these windows can ever be used: skip the rest. Then run the
report for the scenarios being discussed:

```
uv run planner scenarios --back DATE[=LABEL] ...
```

Each "no direct flight on your routes yet" line is an open journey: who, direction
and day. Check the recommended option first, then the others. Do not check more
than about 10 journeys in one go; ask Martin before doing more.

## 1b. Pick the fare source (generic step)

Every flight check goes through one of these sources, in this order. Use the first
that works and record which one it was in `source_url`:

1. **A live-fare helper in this repo**, if one exists. Today:
   `uv run planner fares --month YYYY-MM` (Ryanair only; Wizz is not covered).
   It lists the days inside the time windows with times, price, source and check
   time. It shows the cheapest flight per day and no flight number, so results are
   candidates: still open the airline page for finalists. A route marked
   "NOT live-checked" means the API was blocked or changed: use step 2 for it.
2. **The airline's own site in the browser** (section 2 below).
3. **Momondo**, only to discover other airlines or a cheaper fare.

If none can be checked live, say so and leave the journey open.

## 2. Search in the browser (fast path)

1. **Discover with Ryanair's month view** (Ryanair's own data, one call per route
   per month): navigate to the link from `planner routes`, then read it with
   `javascript_tool`:

   ```js
   JSON.parse(document.body.innerText).outbound.fares.filter(f=>!f.unavailable)
     .map(f=>`${f.departureDate.slice(5,16)}-${f.arrivalDate.slice(11,16)} ${f.price?.value}`).join(' | ')
   ```

   It shows the cheapest flight per day, with its times. Keep the days whose
   times fit the window. Which Italian airports an origin serves:
   `/api/farfnd/v4/oneWayFares?departureAirportIataCode=XXX&outboundDepartureDateFrom=...&outboundDepartureDateTo=...&arrivalCountryCode=it&currency=EUR&market=en-ie`
2. **Confirm only the finalists** on the normal Ryanair select page (below). It
   shows every flight that day, the flight number and seats left. Record from it.
3. **Momondo only for other airlines** (Wizz, LOT, Eurowings); Ryanair is missing
   there. One multi-airport search covers all routes on a day:
   `https://www.momondo.com/flight-search/POZ,WRO,WAW-BLQ,BGY,TSF,VCE/YYYY-MM-DD?fs=stops=0`

Browser tips: `navigate` must be its own call; `browser_batch` cannot act on a
page it just navigated to. Batch the actions after the page loads. Fetch calls
from page JavaScript are blocked: navigate to the JSON URL instead.

### Direct links

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

## 2b. Ground, stays and tolls (finalists only)

- Hire car (Kayak, exact airports and hours): `https://www.kayak.ie/cars/BGY/BLQ/YYYY-MM-DD-09h/YYYY-MM-DD-06h?sort=price_a`
  (same airport twice for a return). Record `pick_up`, `drop_off`.
- Trains: lefrecce.it. Type the station, pick the suggestion, type the date
  (DD/MM/YYYY) in the date box, pick the hour from the time list, then Search.
  Bergamo airport is "Orio al Serio Aeroporto" (Orio Airlink bus included).
- Stays: `https://www.booking.com/searchresults.en-gb.html?ss=Faenza&checkin=YYYY-MM-DD&checkout=YYYY-MM-DD&group_adults=2&group_children=1&age=0&order=price&selected_currency=EUR`
  Record under the place's `quotes:` in accommodation.yaml.
- Italian tolls: calcolopedaggio.it/42_faenza/ (exit field, pick suggestion,
  Calcola). A2 Poland: autostrada-a2.pl/oplaty/cennik-kategoria-1/.
- Drive times and km: Google Maps.

## 3. Record in data/options.yaml

One entry per flight found. `price_eur` is for `seats` people (default 1, one
adult; Basia is an infant on a lap, her fee is added from `infant_fee_eur`).
Add `bag_eur` if the 20 kg bag price for that flight was seen:

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
