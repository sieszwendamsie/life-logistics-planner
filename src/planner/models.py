"""Data models for the three planning files.

Pydantic checks each file when it is loaded, so a typo such as an end date
before its start date fails with a clear message instead of giving wrong plans.
"""

from datetime import date, datetime
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


class RouteTier(BaseModel):
    """A group of direct routes, written from Poznań's side (outbound direction).

    Return flights match the same tier with origin and destination swapped.
    Codes are IATA airport codes, such as POZ or BLQ.
    """

    name: str
    origins: list[str]
    destinations: list[str]


class CarSettings(BaseModel):
    """Martin drives Poznań to Faenza while the family flies."""

    drive_hours: float = Field(default=13, gt=0)
    # Consider the car only for stays at least this long...
    min_stay_days: int = Field(default=21, ge=1)
    # ...and only if no other travel plan is within this many days of the stay.
    clear_days: int = Field(default=7, ge=0)


class Travel(BaseModel):
    """How Martin and the family like to travel."""

    direct_only: bool = True
    # In order of preference: the first tier is the best. Empty means any route.
    route_tiers: list[RouteTier] = Field(default_factory=list)
    # Hours from each airport to home (Poznań or Faenza), used for door-to-door time.
    transfer_hours: dict[str, float] = Field(default_factory=dict)
    car: CarSettings | None = None


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


class Accommodation(BaseModel):
    """One place to stay, with the dates it is free.

    The preferred place is the family house: the planner only travels to its town
    when it is free.

    Each range in `available` works like a booking: `start` is the first night
    (check-in day) and `end` is the check-out day, so the night of `end` is not
    included.
    """

    name: str
    location: str | None = None
    preferred: bool = False
    price_per_night_eur: float | None = Field(default=None, ge=0)
    available: list[DateRange] = Field(default_factory=list)


class AccommodationFile(BaseModel):
    """Contents of accommodation.yaml."""

    accommodation: list[Accommodation]


class TransportOption(BaseModel):
    """One candidate journey, collected during planning.

    `price_eur` is what this journey costs as recorded (for everyone travelling on it).
    `stops` is 0 for a direct flight.
    """

    id: str
    direction: Literal["outbound", "return"]
    carrier: str
    origin: str  # IATA airport code, e.g. POZ
    destination: str  # IATA airport code, e.g. BLQ
    stops: int = Field(default=0, ge=0)
    depart: datetime
    arrive: datetime
    price_eur: float = Field(ge=0)
    source_url: str | None = None

    @model_validator(mode="after")
    def _arrives_after_departure(self) -> "TransportOption":
        if self.arrive <= self.depart:
            raise ValueError(f"{self.id}: arrival must be after departure")
        return self


class OptionsFile(BaseModel):
    """Contents of options.yaml."""

    options: list[TransportOption]
