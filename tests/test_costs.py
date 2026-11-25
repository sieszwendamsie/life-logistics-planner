from datetime import date

from planner.costs import round_trip
from planner.models import CarCosts


def test_short_stay_buys_one_vignette_per_drive_when_cheaper():
    c = round_trip(CarCosts(), date(2027, 1, 31), date(2027, 2, 28))
    # 2 x 1400 km x 6 l/100 km = 168 l at €2.00
    assert c.fuel_eur == 336.0
    assert c.toll_eur == 64.4
    assert c.vignettes == {"CZ": "2 x 1-day", "AT": "2 x 1-day"}
    assert c.total_eur == round(336.0 + 64.4 + 2 * 9.41 + 2 * 9.80, 2)


def test_long_vignette_used_when_it_covers_both_drives_for_less():
    costs = CarCosts(
        vignettes=[
            {"country": "CZ", "days": 1, "price_eur": 12},
            {"country": "CZ", "days": 30, "price_eur": 20},
        ]
    )
    within = round_trip(costs, date(2027, 2, 1), date(2027, 2, 20))
    assert within.vignettes == {"CZ": "1 x 30-day"}
    assert within.vignettes_eur == 20
    # 31 days including both drive days: the 30-day one no longer covers it.
    beyond = round_trip(costs, date(2027, 2, 1), date(2027, 3, 3))
    assert beyond.vignettes == {"CZ": "2 x 1-day"}
