# CLAUDE.md

Instructions Claude reads at the start of every session in this repo. Keep it short.

## What this is
A personal planner for life and hybrid work between Poznań (PL) and Italy: stays,
office days, flights, accommodation, holidays. MVP scope: docs/mvp.md.
How we build it: docs/spec.md (stack, workflow, task list).

## Stack
Claude Code skills + Google Calendar MCP for the workflow; Python 3.12 with `uv`,
Pydantic, Jinja2 for the logic and the HTML report; `pytest` and `ruff` for checks.
No web app in the MVP.

## Commands
- `uv sync`: install dependencies
- `uv run pytest`: run tests
- `uv run ruff check . && uv run ruff format .`: lint and format
- `uv run planner --help`: show commands
- `uv run planner windows` / `uv run planner options`: dates and full options
- `uv run planner scenarios --back DATE[=LABEL] ...`: compare return choices
- `uv run planner report --back ... [--variant "LABEL:solo_max_days=9"]`: scenarios as a page in out/report.html
- `uv run planner routes --month YYYY-MM`: flight times that can work per route, with Ryanair month links
- `uv run planner fares --month YYYY-MM [--route POZ-BGY] [--who martin] [--refresh]`: live Ryanair fares per route inside those windows (cached 12 h; says so if it cannot reach Ryanair)

## Owner
Martin is learning Claude Code from beginner to pro. When you add a new kind of file
or concept (hook, skill, MCP, spec), explain it in a sentence or two. Ask when unsure,
and say so when a better existing tool already does the job.

## Rules
- Prefer existing tools, MCP connectors and libraries over custom code.
- Never purchase, book or confirm anything. Prepare proposals only.
- Flight times and prices only from a live check on the airline's own site; Momondo
  only to discover routes or cheaper fares. Never from schedule sites. If you cannot
  check live, say so instead of guessing.
- Only add events to Google Calendar after Martin approves a plan.
- Never commit secrets, tokens or personal booking data.
- Keep changes small; one feature per branch and pull request.

## Layout
- docs/ : specs and notes (mvp.md is the source of truth for scope, spec.md for how,
  planning-rules.md for every travel rule and the fastest planning steps)
- src/planner/ : Python package (CLI skeleton in place)
- examples/ : fake data, safe to commit (planned)
- data/, out/ : real personal data and reports, gitignored, never commit
- .claude/skills/ : planning workflows (import-calendar reads Google Calendar into data/,
  find-flights checks live flights into data/options.yaml)
