#!/usr/bin/env bash
# PreToolUse hook for the Bash tool: run the planner's checks before `git commit`.
# Claude Code sends the tool call as JSON on stdin. Exit 0 lets the command run;
# exit 2 blocks it and shows stderr to Claude so it can fix the problem first.
# Any other command, or any other project, is left alone.

input=$(cat)

# Only act on `git commit` commands.
echo "$input" | grep -Eq '"command"[[:space:]]*:[[:space:]]*"[^"]*git[[:space:]]+commit' || exit 0

# Only act inside the planner repo (a plugin installed elsewhere must not break other projects).
root="${CLAUDE_PROJECT_DIR:-$PWD}"
cd "$root" 2>/dev/null || exit 0
grep -q 'life-logistics-planner' pyproject.toml 2>/dev/null || exit 0

if ! out=$(uv run pytest -q 2>&1); then
  echo "Tests failed, so the commit was blocked. Fix them, then commit again." >&2
  echo "$out" | tail -25 >&2
  exit 2
fi
if ! out=$(uv run ruff check . 2>&1); then
  echo "ruff found problems, so the commit was blocked." >&2
  echo "$out" | tail -25 >&2
  exit 2
fi
exit 0
