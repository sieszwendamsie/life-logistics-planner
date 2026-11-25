from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from planner.loaders import load_accommodation, load_constraints, load_options
from planner.models import DateRange, StayRules

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def test_example_constraints_load() -> None:
    constraints = load_constraints(EXAMPLES / "constraints.yaml")
    assert constraints.stay_rules.min_stay_days == 21
    assert constraints.family[0].mode == "together"


def test_example_accommodation_loads() -> None:
    data = load_accommodation(EXAMPLES / "accommodation.yaml")
    assert data.accommodation[0].preferred is True


def test_example_options_load() -> None:
    data = load_options(EXAMPLES / "options.yaml")
    assert data.options[0].carrier == "Ryanair"


def test_range_end_before_start_is_rejected() -> None:
    with pytest.raises(ValidationError, match="before start"):
        DateRange(start=date(2027, 2, 2), end=date(2027, 2, 1))


def test_stay_rules_min_above_max_is_rejected() -> None:
    with pytest.raises(ValidationError, match="min_stay_days"):
        StayRules(min_stay_days=30, max_stay_days=21, min_gap_days=28, max_gap_days=35)


def test_family_mode_must_be_known(tmp_path: Path) -> None:
    bad = tmp_path / "constraints.yaml"
    bad.write_text(
        "horizon: {start: 2027-01-01, end: 2027-02-01}\n"
        "stay_rules: {min_stay_days: 1, max_stay_days: 2, min_gap_days: 0, max_gap_days: 1}\n"
        "family:\n  - {start: 2027-01-05, end: 2027-01-06, mode: maybe}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_constraints(bad)


def test_solo_stay_limit_defaults_to_one_week() -> None:
    constraints = load_constraints(EXAMPLES / "constraints.yaml")
    assert constraints.solo_max_days == 7


def test_preferred_accommodation_is_the_family_house() -> None:
    data = load_accommodation(EXAMPLES / "accommodation.yaml")
    preferred = [a for a in data.accommodation if a.preferred]
    assert len(preferred) == 1
    assert preferred[0].location == "Faenza"
