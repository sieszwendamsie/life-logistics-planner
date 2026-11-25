"""Data models for the three planning files.

Pydantic checks each file when it is loaded, so a typo such as an end date
before its start date fails with a clear message instead of giving wrong plans.
"""

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DateRange(BaseModel):
    """A span of days, both ends included."""

    start: date
    end: date

    @model_validator(mode="after")
    def _start_before_end(self) -> "DateRange":
        if self.end < self.start:
            raise ValueError(f"end {self.end} is before start {self.start}")
        return self


class StayRules(BaseModel):
    """How long a stay in Italy should last and how long the gap between stays is."""

    min_stay_days: int = Field(ge=1)
    max_stay_days: int = Field(ge=1)
    min_gap_days: int = Field(ge=0)
    max_gap_days: int = Field(ge=0)
    # Martin never travels on a day he must be in the office in Italy: he arrives
    # at least the day before and leaves at the earliest the day after.
    travel_on_office_days: bool = False

    @model_validator(mode="after")
    def _min_not_above_max(self) -> "StayRules":
        if self.min_stay_days > self.max_stay_days:
            raise ValueError("min_stay_days is larger than max_stay_days")
        if self.min_gap_days > self.max_gap_days:
            raise ValueError("min_gap_days is larger than max_gap_days")
        return self


class FamilyPeriod(DateRange):
    """A period where the family travels together or Martin travels alone."""

    mode: Literal["together", "separately"]


Person = Literal["Martin", "Paula", "Basia"]


class Presence(DateRange):
    """Someone must (or would like to) be in a place on these days, both ends included.

    Usually imported from calendar tags: #PL #IT #UK #any, #Martin #Paula #Basia
    #all, and #must #pref #flex.
    """

    title: str = ""
    where: Literal["PL", "IT", "UK", "any"]
    who: list[Person]
    strength: Literal["must", "pref", "flex"] = "must"


class RouteTier(BaseModel):
    """A group of direct routes, written from Poznań's side (outbound direction).

    Return flights match the same tier with origin and destination swapped.
    Codes are IATA airport codes, such as POZ or BLQ.
    """

    name: str
    origins: list[str]
    destinations: list[str]


class Vignette(BaseModel):
    """A motorway vignette: valid for `days` consecutive days from the first use."""

    country: str  # CZ, AT, ...
    days: int = Field(ge=1)
    price_eur: float = Field(ge=0)


class CarCosts(BaseModel):
    """Assumptions for the cost of one drive between Poznań and Faenza.

    Defaults: Martin's route (about 1400 km, 6 l/100 km diesel), CZ and AT
    vignettes, Italian toll Ugovizza-Tarvisio to Faenza using the free Venice
    bypass (off at Venezia Est, back on at Padova Est). Prices checked on
    2026-11-25; sources in docs/spec.md.
    """

    distance_km: float = Field(default=1400, gt=0)  # one way
    l_per_100km: float = Field(default=6, gt=0)
    diesel_eur_per_l: float = Field(default=2.00, gt=0)  # average along the route
    toll_eur: float = Field(default=32.20, ge=0)  # one way, Italy
    vignettes: list[Vignette] = Field(
        default_factory=lambda: [
            Vignette(country="CZ", days=1, price_eur=9.41),
            Vignette(country="CZ", days=10, price_eur=12.28),
            Vignette(country="CZ", days=30, price_eur=19.65),
            Vignette(country="AT", days=1, price_eur=9.80),
            Vignette(country="AT", days=10, price_eur=13.00),
            Vignette(country="AT", days=61, price_eur=32.60),
        ]
    )


class CarSettings(BaseModel):
    """Martin drives Poznań to Faenza while the family flies."""

    drive_hours: float = Field(default=13, gt=0)
    # Consider the car only for stays at least this long...
    min_stay_days: int = Field(default=21, ge=1)
    # ...and only if no other travel plan is within this many days of the stay.
    clear_days: int = Field(default=7, ge=0)
    # Martin is paid per hour, so he drives only on days he would not work:
    # weekends, public holidays (PL or IT), shutdown and leave days.
    days_off_only: bool = True
    costs: CarCosts = Field(default_factory=CarCosts)


class FamilyFlights(BaseModel):
    """Paula and Basia's flight preferences (soft: they only change the ranking).

    Their flight day may move up to `shift_days` into the stay (later out, earlier
    back) to reach a weekend or a flight at a better time.
    """

    weekend: bool = True  # prefer Saturday or Sunday
    earliest: time = time(10, 0)  # preferred departure window
    latest: time = time(18, 0)
    shift_days: int = Field(default=4, ge=0)
    # Hard limits, door to door (home in Poznań or Faenza): flights that make
    # Paula and Basia leave earlier or arrive later are never proposed.
    leave_home_after: time = time(5, 0)
    arrive_home_by: time = time(20, 0)


class Ride(BaseModel):
    """Taxi (Bolt, Uber) between home and a nearby airport: one ride, any people."""

    hours: float = Field(gt=0)
    price_eur: float = Field(ge=0)
    note: str = ""


class ItalyDrive(BaseModel):
    """Driving between an Italian airport and Faenza (own car or hire car)."""

    km: float = Field(gt=0)
    hours: float = Field(gt=0)
    toll_eur: float = Field(ge=0)  # one way
    note: str = ""


class Travel(BaseModel):
    """How Martin and the family like to travel."""

    direct_only: bool = True
    # In order of preference: the first tier is the best. Empty means any route.
    route_tiers: list[RouteTier] = Field(default_factory=list)
    # Hours from each airport to home (Poznań or Faenza), used for door-to-door time.
    transfer_hours: dict[str, float] = Field(default_factory=dict)
    car: CarSettings | None = None
    # When Martin is in Italy alone and flies into one of these airports, he takes
    # the train (e.g. Marconi Express + train to Faenza) instead of hiring a car.
    # When Paula and Basia are there, a car is always needed.
    train_airports: list[str] = Field(default_factory=lambda: ["BLQ"])
    # Airports near home reached by taxi or local bus (time from transfer_hours).
    # Any other airport in Poland or Germany needs a live-checked bus or train
    # (`ground:` kind transfer). Paula can't drive Martin; no airport hotels.
    home_airports: list[str] = Field(default_factory=lambda: ["POZ"])
    leave_home_after: time = time(5, 0)  # earliest bus/train from home
    airport_margin_hours: float = Field(default=1.5, ge=0)  # at the airport before take-off
    # Basia flies on Paula's lap as an infant (under 2): no seat, an infant fee
    # per one-way flight, with the baby allowance (small bag, child seat, stroller).
    infants: int = Field(default=1, ge=0)
    infant_fee_eur: dict[str, float] = Field(default_factory=dict)  # by airline
    # Large luggage: when Martin drives it goes in the car and Paula and Basia
    # travel light. When nobody drives, each adult checks this many 20 kg bags
    # on every flight, at checked_bag_eur by airline.
    checked_bags_per_adult: int = Field(default=1, ge=0)
    checked_bag_eur: dict[str, float] = Field(default_factory=dict)
    # Door to door: names for the ends of a journey (real places stay in data/).
    home_name: str = "home"
    italy_home_name: str = "Faenza"
    office_name: str = "the office"
    # Arriving on a working day by this time, Martin goes straight to the office.
    office_if_arriving_by: time = time(12, 0)
    # Taxi between home and a nearby airport (e.g. POZ), per ride.
    home_rides: dict[str, Ride] = Field(default_factory=dict)
    # A relative drives Paula and Basia (and Martin, when they fly together)
    # between home and these airports (Google Maps time). No bus or train needed.
    family_lifts: dict[str, Ride] = Field(default_factory=dict)
    # Drives between Italian airports and Faenza (Google Maps time, toll one way).
    italy_drives: dict[str, ItalyDrive] = Field(default_factory=dict)
    italy_fuel_eur_per_l: float = Field(default=2.22, gt=0)
    # From landing to leaving the airport (bags, hire-car desk).
    arrival_buffer_hours: float = Field(default=0.5, ge=0)
    # From Faenza station to the house, when arriving by train.
    station_to_home_hours: float = Field(default=0.4, ge=0)
    family_flights: FamilyFlights = Field(default_factory=FamilyFlights)
    # Try not to fly on long weekends (prices are higher). Soft rule.
    avoid_long_weekends: bool = True


class OnwardTrip(BaseModel):
    """The stay ends by flying on to a third country instead of going home.

    Example: Italy to the UK to visit family for a week, then the UK straight
    back to Poland. The car is never used on such a stay.
    """

    name: str
    airports: list[str]  # IATA codes in the third country, e.g. LTN, STN
    nights: int = Field(ge=1)  # nights spent there before flying home


class Holiday(BaseModel):
    """A public holiday in Poland or Italy (office closed there)."""

    day: date
    country: Literal["PL", "IT"]
    name: str = ""


class Constraints(BaseModel):
    """Contents of constraints.yaml: the rules and fixed dates to plan around."""

    horizon: DateRange
    # The day Martin last came back to Poznań. The next stay starts a gap after it.
    # If unknown, the next stay may start anywhere in the horizon.
    last_return: date | None = None
    stay_rules: StayRules
    office_required: list[DateRange] = Field(default_factory=list)
    poznan_required: list[DateRange] = Field(default_factory=list)
    family: list[FamilyPeriod] = Field(default_factory=list)
    # If the family house (La Suite Elena, Faenza) is not free, Martin may stay alone
    # elsewhere, but for no more than solo_max_days.
    solo_max_days: int = Field(default=7, ge=1)
    # Other trips (holidays, business travel). The car is not used near these.
    other_travel: list[DateRange] = Field(default_factory=list)
    travel: Travel = Field(default_factory=Travel)
    # Set this when the stay being planned continues to a third country.
    onward: OnwardTrip | None = None
    # Who must be where, per person (usually imported from the calendars).
    presence: list[Presence] = Field(default_factory=list)
    # Public holidays in Poland and Italy. Martin prefers to be in Poland on them.
    holidays: list[Holiday] = Field(default_factory=list)
    # Office closed, forced holiday (#shutdown in the Work calendar).
    shutdown: list[DateRange] = Field(default_factory=list)
    # Martin's own leave (#holiday). No work stay is planned over these days.
    leave: list[DateRange] = Field(default_factory=list)

    def day_off(self, d: date) -> bool:
        """True if Martin does not work that day: weekend, holiday, shutdown, leave."""
        if d.weekday() >= 5 or any(h.day == d for h in self.holidays):
            return True
        return any(r.start <= d <= r.end for r in [*self.shutdown, *self.leave])

    def martin_away(self) -> list[DateRange]:
        """Days Martin must be outside Italy (Poznań dates, leave, #PL/#UK must events)."""
        tagged = [
            p
            for p in self.presence
            if "Martin" in p.who and p.where in ("PL", "UK") and p.strength == "must"
        ]
        return [*self.poznan_required, *self.leave, *tagged]

    def martin_italy(self) -> list[DateRange]:
        """Days Martin must be in Italy (office periods and #IT must events)."""
        tagged = [
            p
            for p in self.presence
            if "Martin" in p.who and p.where == "IT" and p.strength == "must"
        ]
        return [*self.office_required, *tagged]

    def family_away(self) -> list[DateRange]:
        """Days Paula or Basia must be outside Italy."""
        return [
            p
            for p in self.presence
            if ({"Paula", "Basia"} & set(p.who))
            and p.where in ("PL", "UK")
            and p.strength == "must"
        ]


class Accommodation(BaseModel):
    """One place to stay, with the dates it is free.

    The preferred place is the family house: the planner only travels to its town
    when it is free.

    Each range works like a booking: `start` is the first night (check-in day) and
    `end` is the check-out day, so the night of `end` is not included.

    `available` lists when the place is free. If it is empty, the place counts as
    free except for the `unavailable` ranges (for example "La Suite - non
    disponibile" blocks in the Travel calendar).
    """

    name: str
    location: str | None = None
    preferred: bool = False
    price_per_night_eur: float | None = Field(default=None, ge=0)
    available: list[DateRange] = Field(default_factory=list)
    unavailable: list[DateRange] = Field(default_factory=list)


class AccommodationFile(BaseModel):
    """Contents of accommodation.yaml."""

    accommodation: list[Accommodation]


class TransportOption(BaseModel):
    """One candidate journey, collected during planning.

    `price_eur` is what this journey costs as recorded (for everyone travelling on it).
    `stops` is 0 for a direct flight.
    """

    id: str
    # outbound: Poland to Italy. return: Italy to Poland.
    # onward: Italy to a third country. home: third country to Poland.
    direction: Literal["outbound", "return", "onward", "home"]
    carrier: str
    origin: str  # IATA airport code, e.g. POZ
    destination: str  # IATA airport code, e.g. BLQ
    stops: int = Field(default=0, ge=0)
    depart: datetime
    arrive: datetime
    price_eur: float = Field(ge=0)
    # How many seats `price_eur` covers. The planner uses the price per seat
    # times the adult seats on the leg (Martin 1, Paula 1, both 2); an infant on
    # a lap pays the airline's infant fee instead (travel.infant_fee_eur).
    seats: int = Field(default=1, ge=1)
    # Live price of a 20 kg checked bag on this flight, per adult (e.g. Ryanair
    # PLUS minus BASIC). Empty: travel.checked_bag_eur for the airline is used.
    bag_eur: float | None = Field(default=None, ge=0)
    source_url: str | None = None
    # When this was seen in a live search (airline site or app, or Momondo).
    # Empty means not verified: the planner shows it as a con.
    checked_on: date | None = None

    @model_validator(mode="after")
    def _arrives_after_departure(self) -> "TransportOption":
        if self.arrive <= self.depart:
            raise ValueError(f"{self.id}: arrival must be after departure")
        return self


class GroundOption(BaseModel):
    """A live-checked hire car or train in Italy (Kayak, Trenitalia...).

    Hire car: `start` is the pick-up day, `end` the drop-off day. Train: `start`
    is the travel day (`end` empty). `price_eur` is the total for that booking.
    """

    id: str
    kind: Literal["car_hire", "train", "transfer"]
    start: date
    end: date | None = None
    # transfer only: bus or train between home and a far airport, per person.
    airport: str | None = None  # IATA code of the airport it serves
    depart: datetime | None = None
    arrive: datetime | None = None
    # car_hire only: airports (IATA) where the car is picked up and dropped off.
    # When set, the quote is only used if they match the flights.
    pick_up: str | None = None
    drop_off: str | None = None
    where: str = ""  # e.g. "BGY to BGY" or "Faenza to Bergamo airport"
    detail: str = ""  # e.g. "Ford Fiesta or similar, DiscoverCars" or train times
    price_eur: float = Field(ge=0)
    source_url: str | None = None
    checked_on: date | None = None


class OptionsFile(BaseModel):
    """Contents of options.yaml."""

    options: list[TransportOption]
    ground: list[GroundOption] = Field(default_factory=list)
