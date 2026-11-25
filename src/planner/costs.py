"""Cost of driving Poznań to Faenza and back: fuel, vignettes and Italian tolls.

Vignettes are chosen per country: either one short vignette for each drive, or
one long vignette that covers both drives, whichever is cheaper.
"""

from dataclasses import dataclass, field
from datetime import date

from planner.models import CarCosts


@dataclass
class CarCost:
    fuel_eur: float
    toll_eur: float
    vignettes_eur: float
    # What was bought per country, e.g. {"CZ": "2 x 1-day", "AT": "1 x 61-day"}.
    vignettes: dict[str, str] = field(default_factory=dict)

    @property
    def total_eur(self) -> float:
        return round(self.fuel_eur + self.toll_eur + self.vignettes_eur, 2)

    def text(self) -> str:
        v = ", ".join(f"{c} {how}" for c, how in self.vignettes.items())
        return (
            f"Driving there and back about €{self.total_eur:.0f}: fuel €{self.fuel_eur:.0f}, "
            f"Italian tolls €{self.toll_eur:.0f}, vignettes €{self.vignettes_eur:.0f} ({v})"
        )


def round_trip(costs: CarCosts, out_day: date, back_day: date) -> CarCost:
    """Cost of driving out on `out_day` and back on `back_day`."""
    litres = 2 * costs.distance_km * costs.l_per_100km / 100
    span = (back_day - out_day).days + 1  # both drive days included
    total = 0.0
    chosen: dict[str, str] = {}
    for country in dict.fromkeys(v.country for v in costs.vignettes):
        own = [v for v in costs.vignettes if v.country == country]
        one = min(own, key=lambda v: v.price_eur)
        best_price, best = 2 * one.price_eur, f"2 x {one.days}-day"
        for v in own:
            if v.days >= span and v.price_eur < best_price:
                best_price, best = v.price_eur, f"1 x {v.days}-day"
        total += best_price
        chosen[country] = best
    return CarCost(
        fuel_eur=round(litres * costs.diesel_eur_per_l, 2),
        toll_eur=round(2 * costs.toll_eur, 2),
        vignettes_eur=round(total, 2),
        vignettes=chosen,
    )
