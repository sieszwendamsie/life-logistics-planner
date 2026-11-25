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


class Constraints(BaseModel):
    """Contents of constraints.yaml: the rules and fixed dates to plan around."""

    horizon: DateRange
    stay_rules: StayRules
    office_required: list[DateRange] = Field(default_factory=list)
    poznan_required: list[DateRange] = Field(default_factory=list)
    family: list[FamilyPeriod] = Field(default_factory=list)
    # Dates the family house in Italy can be used. Outside these dates Martin may
    # still stay alone, but only for solo_max_days at most.
    family_house_available: list[DateRange] = Field(default_factory=list)
    solo_max_days: int = Field(default=7, ge=1)


class Accommodation(BaseModel):
    """One place to stay, with the dates it is free."""

    name: str
    preferred: bool = False
    price_per_night_eur: float | None = Field(default=None, ge=0)
    available: list[DateRange] = Field(default_factory=list)


class AccommodationFile(BaseModel):
    """Contents of accommodation.yaml."""

    accommodation: list[Accommodation]


class TransportOption(BaseModel):
    """One candidate journey, collected during planning."""

    id: str
    carrier: str
    origin: str
    destination: str
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
