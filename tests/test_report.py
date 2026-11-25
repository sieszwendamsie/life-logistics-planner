from datetime import date
from pathlib import Path

from planner.cli import main
from planner.loaders import load_accommodation, load_constraints, load_options
from planner.report import build_view, render, scenario

EX = Path("examples")


def _data():
    return (
        load_constraints(EX / "constraints.yaml"),
        load_accommodation(EX / "accommodation.yaml"),
        load_options(EX / "options.yaml"),
    )


def test_scenario_window_follows_day_back() -> None:
    c, acc, tr = _data()
    back = c.last_return or date(2027, 1, 6)
    s = scenario(c, acc, tr, back, "test flight")
    assert s.earliest == back.fromordinal(back.toordinal() + c.stay_rules.min_gap_days)
    assert all(o.window.start >= s.earliest for o in s.options)


def test_view_has_timeline_rows_inside_axis_and_one_recommendation() -> None:
    c, acc, tr = _data()
    scenarios = [scenario(c, acc, tr, None)]
    views = build_view(scenarios, c, acc)
    options = [o for v in views for o in v.options]
    assert options, "examples should give at least one option"
    assert sum(o.recommended for o in options) == 1
    for o in options:
        assert [r.who for r in o.rows] == ["Martin", "Paula + Basia"]
        for r in o.rows:
            for seg in r.segments:
                assert 0 <= seg.left <= 100 and seg.left + seg.width <= 100.001


def test_render_contains_options_and_escapes() -> None:
    c, acc, tr = _data()
    html = render([scenario(c, acc, tr, None, "<b>x</b>")], c, acc, date(2026, 11, 25))
    assert "<title>Next stay plan</title>" in html
    assert "Option A" in html
    assert "<b>x</b>" not in html  # labels are escaped


def test_report_command_writes_file(tmp_path: Path) -> None:
    out = tmp_path / "report.html"
    code = main(
        [
            "report",
            "--constraints",
            str(EX / "constraints.yaml"),
            "--accommodation",
            str(EX / "accommodation.yaml"),
            "--transport",
            str(EX / "options.yaml"),
            "--out",
            str(out),
        ]
    )
    assert code == 0
    assert "Compare" in out.read_text()
