from datetime import date
from pathlib import Path

import pytest

from planner.cli import main
from planner.loaders import load_constraints
from planner.models import Constraints
from planner.windows import find_windows

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def make(**overrides: object) -> Constraints:
    base: dict[str, object] = {
        "horizon": {"start": "2027-01-01", "end": "2027-06-30"},
        "last_return": "2027-01-01",
        "stay_rules": {
            "min_stay_days": 21,
            "max_stay_days": 22,
            "min_gap_days": 28,
            "max_gap_days": 29,
        },
    }
    base.update(overrides)
    return Constraints.model_validate(base)


def test_windows_follow_gap_and_length_rules() -> None:
    windows = find_windows(make())
    assert {(w.start, w.days) for w in windows} == {
        (date(2027, 1, 29), 21),
        (date(2027, 1, 29), 22),
        (date(2027, 1, 30), 21),
        (date(2027, 1, 30), 22),
    }


def test_window_overlapping_poznan_date_is_dropped() -> None:
    windows = find_windows(make(poznan_required=[{"start": "2027-02-20", "end": "2027-02-20"}]))
    # Only the shortest window from the 29th ends before 20 Feb.
    assert [(w.start, w.end) for w in windows] == [(date(2027, 1, 29), date(2027, 2, 19))]


def test_office_period_must_be_fully_inside() -> None:
    office = [{"start": "2027-02-19", "end": "2027-02-21"}]
    windows = find_windows(make(office_required=office))
    # Windows ending 19 or 20 Feb would cut through the office period.
    assert all(w.end >= date(2027, 2, 21) for w in windows)
    assert all(len(w.office_covered) == 1 for w in windows)


def test_no_travel_on_office_days() -> None:
    office = [{"start": "2027-02-03", "end": "2027-02-13"}]
    windows = find_windows(make(office_required=office))
    assert windows
    assert all(w.start < date(2027, 2, 3) and w.end > date(2027, 2, 13) for w in windows)


def test_windows_stay_inside_horizon_month_end() -> None:
    windows = find_windows(make(horizon={"start": "2027-01-01", "end": "2027-02-20"}))
    assert all(w.end <= date(2027, 2, 20) for w in windows)
    assert [(w.start, w.end) for w in windows] == [
        (date(2027, 1, 29), date(2027, 2, 19)),
        (date(2027, 1, 29), date(2027, 2, 20)),
        (date(2027, 1, 30), date(2027, 2, 20)),
    ]


def test_no_last_return_searches_whole_horizon() -> None:
    windows = find_windows(
        make(last_return=None, horizon={"start": "2027-01-01", "end": "2027-01-23"})
    )
    assert {w.start for w in windows} == {date(2027, 1, 1), date(2027, 1, 2)}


def test_example_file_has_windows() -> None:
    windows = find_windows(load_constraints(EXAMPLES / "constraints.yaml"))
    assert windows
    assert all(len(w.office_covered) == 1 for w in windows)


def test_cli_windows_prints_table(capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(["windows", "--constraints", str(EXAMPLES / "constraints.yaml"), "--limit", "3"]) == 0
    )
    out = capsys.readouterr().out
    assert "feasible windows" in out
    assert "depart" in out


def test_cli_windows_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["windows", "--constraints", str(tmp_path / "nope.yaml")]) == 1
    assert "No constraints file" in capsys.readouterr().out
