"""Command line entry point: `planner`.

For now it only shows help and the version. Commands such as `windows` and
`report` arrive in later tasks (see docs/spec.md).
"""

import argparse

from planner import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="planner",
        description="Plan stays, office days and travel between Poznań and Italy.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
