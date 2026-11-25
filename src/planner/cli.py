"""Command line entry point: `planner`.

Commands:
  windows   list feasible date windows for the next stay in Italy
  options   combine windows, accommodation and journeys into a short list of options
"""

import argparse
from pathlib import Path

from planner import __version__
from planner.loaders import load_accommodation, load_constraints, load_options
from planner.options import build_options, shortlist
from planner.windows import find_windows

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
    return parser


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
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "windows":
        return _cmd_windows(args)
    if args.command == "options":
        return _cmd_options(args)
    parser.print_help()
    return 0
