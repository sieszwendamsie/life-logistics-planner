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

## Commands (available once task 1 in docs/spec.md lands)
- `uv sync`: install dependencies
- `uv run pytest`: run tests
- `uv run ruff check . && uv run ruff format .`: lint and format
- `uv run planner windows` / `uv run planner report`: plan and write out/report.html

## Owner
Martin is learning Claude Code from beginner to pro. When you add a new kind of file
or concept (hook, skill, MCP, spec), explain it in a sentence or two. Ask when unsure,
and say so when a better existing tool already does the job.

## Rules
- Prefer existing tools, MCP connectors and libraries over custom code.
- Never purchase, book or confirm anything. Prepare proposals only.
- Only add events to Google Calendar after Martin approves a plan.
- Never commit secrets, tokens or personal booking data.
- Keep changes small; one feature per branch and pull request.

## Layout
- docs/ : specs and notes (mvp.md is the source of truth for scope, spec.md for how)
- planner/ : Python package (planned)
- examples/ : fake data, safe to commit (planned)
- data/, out/ : real personal data and reports, gitignored, never commit
- .claude/skills/ : planning workflows (planned)
