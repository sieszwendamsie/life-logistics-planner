"""Command line entry point: `planner`.

Commands:
  windows   list feasible date windows for the next stay in Italy
  options   combine windows, accommodation and journeys into a short list of options
  scenarios compare what each possible return date means for the next stay
  report    the same as scenarios, drawn as one HTML page (out/report.html)
  routes    which flight times can work per route (search only inside these)
  year      draft plan of a whole year: holiday proposals and stays in Faenza
"""

import argparse
from datetime import date
from pathlib import Path

from planner import __version__
from planner.loaders import load_accommodation, load_constraints, load_options
from planner.options import Option, build_options, shortlist
from planner.report import parse_variant, render, scenario, write
from planner.routes import route_windows, table
from planner.windows import find_windows
from planner.year import build_year, text

DEFAULT_CONSTRAINTS = Path("data/constraints.yaml")
DEFAULT_ACCOMMODATION = Path("data/accommodation.yaml")
DEFAULT_TRANSPORT = Path("data/options.yaml")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="planner",
        description="Plan stays, office days and travel between Poznań and Italy.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    windows = sub.add_parser("windows", help="list feasible date windows for the next stay")
    windows.add_argument(
        "--constraints",
        type=Path,
        default=DEFAULT_CONSTRAINTS,
        help=f"constraints file (default: {DEFAULT_CONSTRAINTS})",
    )
    windows.add_argument("--limit", type=int, default=10, help="how many windows to show")

    options = sub.add_parser("options", help="short list of full options to compare")
    for name, default in (
        ("constraints", DEFAULT_CONSTRAINTS),
        ("accommodation", DEFAULT_ACCOMMODATION),
        ("transport", DEFAULT_TRANSPORT),
    ):
        options.add_argument(
            f"--{name}", type=Path, default=default, help=f"{name} file (default: {default})"
        )
    options.add_argument("--top", type=int, default=3, help="how many options to show")

    scen = sub.add_parser(
        "scenarios", help="compare next-stay options for several possible return dates"
    )
    for name, default in (
        ("constraints", DEFAULT_CONSTRAINTS),
        ("accommodation", DEFAULT_ACCOMMODATION),
        ("transport", DEFAULT_TRANSPORT),
    ):
        scen.add_argument(
            f"--{name}", type=Path, default=default, help=f"{name} file (default: {default})"
        )
    scen.add_argument(
        "--back",
        action="append",
        required=True,
        metavar="DATE[=LABEL]",
        help="a possible day back in Poznań, e.g. 2027-01-02='FR 2194 12:00'. Repeat it.",
    )
    scen.add_argument("--top", type=int, default=3, help="options to show per scenario")
    scen.add_argument(
        "--variant",
        action="append",
        default=[],
        metavar="LABEL:FIELD=VALUE,...",
        help="also try each day back with changed rules, e.g. 'Drive 31 Jan:solo_max_days=9'",
    )

    rep = sub.add_parser("report", help="write the options and scenarios as an HTML page")
    for name, default in (
        ("constraints", DEFAULT_CONSTRAINTS),
        ("accommodation", DEFAULT_ACCOMMODATION),
        ("transport", DEFAULT_TRANSPORT),
    ):
        rep.add_argument(
            f"--{name}", type=Path, default=default, help=f"{name} file (default: {default})"
        )
    rep.add_argument(
        "--back",
        action="append",
        default=[],
        metavar="DATE[=LABEL]",
        help="a possible day back in Poznań (repeat it). Default: last_return.",
    )
    rep.add_argument("--top", type=int, default=3, help="options per scenario")
    rep.add_argument(
        "--variant",
        action="append",
        default=[],
        metavar="LABEL:FIELD=VALUE,...",
        help="also try each day back with changed rules, e.g. 'Drive 31 Jan:solo_max_days=9'",
    )
    rep.add_argument("--out", type=Path, default=Path("out/report.html"), help="output file")

    routes = sub.add_parser("routes", help="flight times that can work, per route")
    routes.add_argument(
        "--constraints",
        type=Path,
        default=DEFAULT_CONSTRAINTS,
        help=f"constraints file (default: {DEFAULT_CONSTRAINTS})",
    )
    routes.add_argument(
        "--month", help="YYYY-MM: also print Ryanair's per-day fares link for each route"
    )
    year = sub.add_parser("year", help="draft plan of a whole year: holidays and stays")
    for name, default in (
        ("constraints", DEFAULT_CONSTRAINTS),
        ("accommodation", DEFAULT_ACCOMMODATION),
    ):
        year.add_argument(
            f"--{name}", type=Path, default=default, help=f"{name} file (default: {default})"
        )
    year.add_argument("--out", type=Path, help="also write the plan as an HTML page here")
    return parser


def _cmd_year(args: argparse.Namespace) -> int:
    for path in (args.constraints, args.accommodation):
        if not path.exists():
            print(f"No file at {path}. The examples/ folder has a template for each file.")
            return 1
    c = load_constraints(args.constraints)
    if c.year_plan is None:
        print("No year_plan section in the constraints. See examples/constraints.yaml.")
        return 1
    result = build_year(c, load_accommodation(args.accommodation))
    print(text(c, result))
    if args.out:
        from planner.year_report import render_year

        print(f"Wrote {write(render_year(c, result), args.out)}")
    return 0


def _cmd_routes(args: argparse.Namespace) -> int:
    if not args.constraints.exists():
        print(f"No file at {args.constraints}. See examples/constraints.yaml.")
        return 1
    print(table(route_windows(load_constraints(args.constraints).travel), args.month))
    return 0


def _cmd_windows(args: argparse.Namespace) -> int:
    if not args.constraints.exists():
        print(
            f"No constraints file at {args.constraints}. "
            "Try --constraints examples/constraints.yaml"
        )
        return 1
    windows = find_windows(load_constraints(args.constraints))
    if not windows:
        print("No feasible window. Loosen the stay rules or check the fixed dates.")
        return 1
    print(f"{len(windows)} feasible windows, showing {min(args.limit, len(windows))}:")
    print(f"{'depart':<12}{'return':<12}{'days':>5}  office periods covered")
    for w in windows[: args.limit]:
        print(
            f"{w.start.isoformat():<12}{w.end.isoformat():<12}{w.days:>5}  {len(w.office_covered)}"
        )
    return 0


def _print_option(label: str, o: Option) -> None:
    w = o.window
    if o.martin_drives:
        mode = "Martin drives, Paula and Basia fly"
    elif o.family_together:
        mode = "everyone flies, family together"
    else:
        mode = "everyone flies, travel separately"
    print(f"Option {label}: {w.start} to {w.end} ({w.days} nights), {mode}")
    print(
        f"  Door to door, both ways: Martin {o.martin_hours:.1f} h, "
        f"Paula and Basia {o.family_hours:.1f} h. About EUR {o.total_cost_eur:.0f}"
    )
    for leg in o.legs:
        if leg.mode == "car":
            got = f"car, about {leg.hours:.0f} h"
        elif leg.choice is None:
            got = "no direct flight on your routes yet"
        else:
            f = leg.choice
            got = (
                f"{f.carrier} {f.origin}-{f.destination} {f.depart:%H:%M}, "
                f"{leg.hours:.1f} h door to door, route choice {leg.tier}"
            )
        print(f"  {leg.day} {leg.direction:<8} {leg.who:<8} {got}")
    for pro in o.pros:
        print(f"  + {pro}")
    for con in o.cons:
        print(f"  - {con}")
    print()


def _cmd_options(args: argparse.Namespace) -> int:
    for path in (args.constraints, args.accommodation, args.transport):
        if not path.exists():
            print(f"No file at {path}. The examples/ folder has a template for each file.")
            return 1
    constraints = load_constraints(args.constraints)
    built = build_options(
        constraints,
        load_accommodation(args.accommodation),
        load_options(args.transport),
        find_windows(constraints),
    )
    best = shortlist(built, n=args.top)
    if not best:
        print("No feasible option. Check the family house dates and solo_max_days.")
        return 1
    for label, o in zip("ABCDEFGHIJ", best, strict=False):
        _print_option(label, o)
    return 0


def _parse_back(item: str) -> tuple[date, str]:
    day_text, _, name = item.partition("=")
    return date.fromisoformat(day_text), name


def _cases(
    backs: list[str], variants: list[str], default: date | None = None
) -> list[tuple[date | None, str, dict[str, object]]]:
    """Every day back combined with every rule variant (or the rules as they are)."""
    days = [_parse_back(item) for item in backs] or [(default, "")]
    rules = [parse_variant(v) for v in variants] or [("", {})]
    return [
        (back, " · ".join(x for x in (name, label) if x), changes)
        for back, name in days
        for label, changes in rules
    ]


def _cmd_scenarios(args: argparse.Namespace) -> int:
    for path in (args.constraints, args.accommodation, args.transport):
        if not path.exists():
            print(f"No file at {path}. The examples/ folder has a template for each file.")
            return 1
    base = load_constraints(args.constraints)
    accommodation = load_accommodation(args.accommodation)
    transport = load_options(args.transport)
    for back, name, changes in _cases(args.back, args.variant):
        s = scenario(base, accommodation, transport, back, name, args.top, changes)
        title = f"Back in Poznań {back:%a %d %b %Y}" + (f" ({name})" if name else "")
        print("=" * len(title))
        print(title)
        print("=" * len(title))
        print(f"Next stay can start {s.earliest:%a %d %b} to {s.latest:%a %d %b}.")
        if not s.options:
            print("No feasible option.\n")
            continue
        print()
        for label, o in zip("ABCDEFGHIJ", s.options, strict=False):
            _print_option(label, o)
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    for path in (args.constraints, args.accommodation, args.transport):
        if not path.exists():
            print(f"No file at {path}. The examples/ folder has a template for each file.")
            return 1
    base = load_constraints(args.constraints)
    accommodation = load_accommodation(args.accommodation)
    transport = load_options(args.transport)
    scenarios = [
        scenario(base, accommodation, transport, back, name, args.top, changes)
        for back, name, changes in _cases(args.back, args.variant, base.last_return)
    ]
    path = write(render(scenarios, base, accommodation), args.out)
    print(f"Wrote {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "windows":
        return _cmd_windows(args)
    if args.command == "options":
        return _cmd_options(args)
    if args.command == "scenarios":
        return _cmd_scenarios(args)
    if args.command == "report":
        return _cmd_report(args)
    if args.command == "routes":
        return _cmd_routes(args)
    if args.command == "year":
        return _cmd_year(args)
    parser.print_help()
    return 0
