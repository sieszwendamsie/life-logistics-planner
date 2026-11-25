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
    assert sum(o.recommended for o in options) <= 1
    # Only options whose flights were all checked live can be recommended.
    assert all(not o.open_checks for o in options if o.recommended)
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


def test_variant_changes_rules_for_one_scenario() -> None:
    from planner.report import parse_variant

    label, changes = parse_variant("Drive early:solo_max_days=9,avoid=true")
    assert label == "Drive early" and changes == {"solo_max_days": 9, "avoid": True}
    c, acc, tr = _data()
    s = scenario(c, acc, tr, None, "x", changes={"solo_max_days": 2})
    assert all(o.solo_nights <= 2 for o in s.options)


def test_unchecked_flights_are_never_recommended() -> None:
    c, acc, tr = _data()
    unchecked = tr.model_copy(
        update={"options": [o.model_copy(update={"checked_on": None}) for o in tr.options]}
    )
    views = build_view([scenario(c, acc, unchecked, None)], c, acc)
    assert not any(o.recommended for v in views for o in v.options)


def test_variant_can_switch_off_the_car() -> None:
    from planner.report import parse_variant

    _, changes = parse_variant("C: fly:travel.car=none")
    c, acc, tr = _data()
    s = scenario(c, acc, tr, None, "C", changes=changes)
    assert not any(o.martin_drives for o in s.options)
