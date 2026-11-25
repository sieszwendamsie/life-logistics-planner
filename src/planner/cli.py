"""Command line entry point: `planner`.

Commands:
  windows   list feasible date windows for the next stay in Italy
"""

import argparse
from pathlib import Path

from planner import __version__
from planner.loaders import load_constraints
from planner.windows import find_windows

DEFAULT_CONSTRAINTS = Path("data/constraints.yaml")


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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "windows":
        return _cmd_windows(args)
    parser.print_help()
    return 0
