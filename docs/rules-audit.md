# Rules audit (25 Nov 2026)

Every rule in `docs/planning-rules.md` and in project memory, checked against the
code in `src/planner/` and the tests in `tests/`. Three lists: what is enforced and
tested, what is missing or only partly done, and the assumptions Martin should
confirm. Two cheap tests were added with this audit (marked **new**).

## 1. Enforced and tested

| Rule | Where in code | Test |
|---|---|---|
| La Suite is preferred; family goes only when it is free | `build_options`, `_free_ranges` | `test_whole_stay_in_house_is_family_together...`, `test_house_not_free_at_all_drops_the_window` |
| Martin alone elsewhere: at most `solo_max_days` (7) nights | `build_options` | `test_too_many_solo_nights_drops_the_window` |
| City break: family up to 3 nights early on a day off, priced from a quote | `_bridge`, `_legs` | `test_family_comes_early_on_a_weekend_for_a_short_city_break` |
| No travel to Italy on a required office day | `windows.py` | `test_no_travel_on_office_days` |
| Required office / Poznań periods respected | `windows.py`, `presence` | `test_office_period_must_be_fully_inside`, `test_presence.py` |
| Car only on days off; Polish holidays are not days off | `_car_allowed`, `Constraints.day_off` | `test_car_only_on_days_off`, **new** `test_days_off_are_weekends_italian_holidays_shutdown_and_leave` |
| Car not used near other travel or on short stays | `_car_allowed` | `test_no_car_near_other_travel_or_short_stay` |
| Driving cost: fuel, cheapest CZ and AT vignettes, Italian toll | `costs.round_trip` | `test_costs.py` |
| Direct flights only | `_flight` | `test_indirect_flights_are_ignored` |
| Route tiers in order; Modlin never (not in any tier); otherwise "ask Martin" | `_tier` | `test_better_route_tier_wins_over_price`, `test_route_outside_tiers_is_missing` (uses WMI), `test_missing_journey_is_a_con_not_a_drop` |
| Paula and Basia: leave home after 05:00, home by 20:00 | `_family_window_ok` | `test_family_window_drops_too_early_or_too_late_flights`, `test_family_flight_too_late_is_not_used` |
| Their weekend / 10:00-18:00 preferences (ranking and cons) | `_soft_cons`, `_family_flight` | `test_family_flight_moves_to_the_weekend_in_good_hours` |
| Relatives' lift to WRO/WAW, fuel + tolls counted there and back | `_extras` | `test_family_window_drops...` (asserts the cost) |
| Far airport for Martin alone needs a live-checked bus or train, after 05:00, 1.5 h before take-off | `_transfer` | `test_far_airport_needs_a_checked_bus_or_train` |
| Martin alone into BLQ takes the train; otherwise hire car | `_uses_train`, `_ground` | `test_martin_alone_into_bologna_takes_the_train` |
| Hire-car quote must match pick-up and drop-off airports | `_ground` | `test_ground_costs_only_from_live_checks` |
| Infant fee per flight; bags only when nobody drives; bag price from the flight beats the airline table | `build_options` costs | `test_car_option_when_no_other_travel_nearby`, `test_flight_bag_price_beats_airline_table` |
| Unchecked flight or ground leg is "not a proposal yet", never recommended | `Option.missing_legs`, `open_ground` | `test_unchecked_flight_is_a_con`, `test_unchecked_flights_are_never_recommended` |
| Margins: 1.5 h before take-off, 0.5 h after landing, in door-to-door time | `_journey`, `_door_hours` | `test_whole_stay_in_house...` (8 h), `test_better_route_tier_wins...` |
| Door to door ends at the office for a weekday arrival before 12:00, else Faenza | `_journey` | **new** `test_arriving_on_a_working_morning_goes_straight_to_the_office` |
| Martin flying on a working day is a con (unpaid hours) | `_soft_cons` | `test_martin_flying_on_a_working_day_is_a_con` |
| Avoid long weekends; note being in Italy on public holidays | `holidays.py`, `_soft_cons` | `test_holidays.py` |
| Total cost by kind | `build_options` | `test_options.py` (several) |

## 2. Missing or only partly enforced

Bigger items are listed, not built.

1. **Yearly holiday rules** (about 4 weeks around the summer shutdown, 2 weeks in
   March or April, 1-2 extra days at the winter shutdown, long weekends via bridge
   days). Not in code. The 2027 plan exists as a draft (PR #20) built with the
   year-plan skill, not checked by tests. *Bigger.*
2. **Remote/office split of 55-65 %.** Not computed anywhere. *Bigger.*
3. **"Prefer being in Poland on public holidays"** is only a con (a note), not a
   ranking weight. Probably fine; confirm.
4. **Never sleep near the airport.** Only implied: a bus or train must run on the
   flight day. No explicit check. *Cheap but low value.*
5. **Paula and Basia: arrival may shift up to 4 days; prefer no shift.** The shift
   limit is enforced, the "prefer no shift" part is not a ranking factor. *Medium.*
6. **Tiers 1 and 2 contain no Modlin by design**, but there is no test using the
   real tier list from `examples/constraints.yaml` (the test uses a small list).
   *Cheap, low value.*
7. **Live-data rules (source, check date, airline site only)** are process rules in
   the skills. The code only checks that `checked_on` is set, not that
   `source_url` is an airline site. *Medium: could warn on a missing `source_url`.*
8. **Rules that live only in skills and docs** (Kayak for hire cars, Trenitalia,
   FlixBus, EU Oil Bulletin, calcolopedaggio.it). Not testable in the planner.
9. **Calendar tag conventions** (`#PL`, `#Martin`, `#must`...) are handled by the
   import-calendar skill; the loader only validates the resulting YAML.
10. **No test uses the public-holiday cons with the shutdown days** (a shutdown day
    counts as a day off for car and flight cons, tested only through `day_off`).

## 3. Assumptions Martin should confirm

| # | Assumption | Where | Current value |
|---|---|---|---|
| 1 | Airport buffers: 1.5 h before take-off, 0.5 h after landing | `airport_margin_hours`, `arrival_buffer_hours` | 1.5 / 0.5 |
| 2 | A hire car burns the same as the own car: 6 l/100 km | `_extras` reuses `car.costs.l_per_100km` | 6 l/100 km |
| 3 | Hire-car fuel price in Italy | `italy_fuel_eur_per_l` | €2.22 |
| 4 | Relatives' cars also burn 6 l/100 km (falls back to 6 l when no car is set) | `_extras` | 6 l/100 km, PL diesel €1.75 |
| 5 | One 20 kg checked bag per adult per flight, when nobody drives | `checked_bags_per_adult` | 1 |
| 6 | One infant fee per flight for Basia, no seat | `infants`, `infant_fee_eur` | 1 |
| 7 | Return bus or train must leave at least 45 min after landing | hard-coded in `_transfer` | 45 min |
| 8 | Weekday arrival counts as "straight to the office" if Martin is there by 12:00 | `office_if_arriving_by` | 12:00 |
| 9 | Station to home in Faenza | `station_to_home_hours` | 0.4 h |
| 10 | Diesel €2.00/l on the Poznań-Faenza drive, 13 h driving | `car.costs`, `drive_hours` | €2.00, 13 h |
| 11 | Car needs at least 21 days' stay and 7 clear days from other travel | `car.min_stay_days`, `clear_days` | 21 / 7 |
| 12 | A window must leave 28-35 days between stays (example values) | `stay_rules` | check your real file |
| 13 | Italian toll exits (Venezia Est off, Padova Est on) | `car.costs.toll_eur` | €32.20, "not confirmed yet" in memory |
| 14 | "Long weekend" = a public holiday on Monday or Thursday/Friday bridge | `holidays.py` | as tested |

Suggested next step: confirm or correct items 1-5 and 7-8 (they change totals and
door-to-door times most), then decide whether gaps 1 and 2 are worth building.
