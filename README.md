# Life logistics planner

A personal logistics planner for life and hybrid work between Poznań and Italy. It
plans stays, office vs remote days, travel itineraries and holidays, and proposes a
few realistic options to compare instead of a single answer. It never books or pays.

**Status:** MVP in progress. Planning a stay, comparing return dates, the HTML
report, live flight checks, and a draft year plan with holiday proposals all work.
Approving a plan into Google Calendar (spec task 9) is not built yet.

## How it works

Claude Code is the app. Skills read the calendars (Google Calendar MCP) and check
live flights; a small Python package does the date and cost maths and writes an
HTML report. Real data lives in `data/` and reports in `out/`; both are gitignored.
Fake data with the same shape is in `examples/`.

## Run it

```
uv sync                      # install dependencies
uv run pytest                # tests
uv run ruff check . && uv run ruff format .
uv run planner --help        # windows, options, scenarios, report, routes, year
```

See [CLAUDE.md](CLAUDE.md) for what each command does.

## Skills

The `life-logistics` plugin in `plugin/life-logistics/` holds the skills
(`import-calendar`, `plan-next-stay`, `plan-year`, `find-flights`) and a hook that
runs the tests before `git commit`. `.claude/skills/` links to them.

## Docs

- [docs/mvp.md](docs/mvp.md): what the MVP is and why (scope, source of truth)
- [docs/spec.md](docs/spec.md): how it is built (stack, workflow, task list)
- [docs/planning-rules.md](docs/planning-rules.md): every travel and holiday rule
- [docs/rules-audit.md](docs/rules-audit.md): which rules the code enforces
- [docs/lessons/](docs/lessons/skills-hooks-plugins.md): short Claude Code lessons

## Principles

- Search, compare and propose on its own. Never book or pay without explicit approval.
- Reuse existing tools (Google Calendar, Maps, flight and stay search) before building new ones.
