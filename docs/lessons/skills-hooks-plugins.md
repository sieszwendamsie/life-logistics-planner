# Lesson: how CLAUDE.md, skills, hooks and plugins fit together

You are learning Claude Code, so this lesson uses this repo as the example.
Five minutes to read. The one-line version:

> **CLAUDE.md** is what Claude always knows. **Skills** are how-to guides it
> opens when needed. **Hooks** are rules the program enforces, whatever Claude
> decides. **Plugins** are the box that ships all of them together.

## 1. CLAUDE.md: always loaded, keep it short

`CLAUDE.md` (repo root) is read at the start of every session. It holds facts and
rules that apply to everything: what the project is, the commands, and your
non-negotiables ("never book anything", "live prices only").

Because it is always in Claude's context, every line costs attention on every
task. Keep it short and point to longer documents (`docs/planning-rules.md`)
instead of copying them in.

## 2. Skills: a workflow loaded only when it matters

A skill is a folder with a `SKILL.md`. The top (the *frontmatter*) has a `name`
and a `description`. Claude sees only the descriptions all the time, and loads
the full body when a task matches. That keeps the always-on context small.

This repo has four, in `plugin/life-logistics/skills/`:

| Skill | When it runs |
|---|---|
| `import-calendar` | calendars changed, or before planning |
| `plan-next-stay` | "plan the next stay", "when can we go" |
| `plan-year` | "plan the year", holiday proposals |
| `find-flights` | a journey still says "Flight not checked yet" |

`plan-next-stay` is the conductor: it calls the others in order. Write a skill
when you have explained the same multi-step procedure to Claude twice.

Rule of thumb: a skill describes *what to do and how to decide*. The heavy
calculation stays in Python (`uv run planner ...`), where it is tested.

## 3. Hooks: guarantees, not requests

CLAUDE.md and skills are *advice*: Claude follows them almost always. A **hook**
is a command the Claude Code program itself runs at a fixed moment (before a
tool call, after one, at session start, and so on). Claude cannot forget it.

Ours is a `PreToolUse` hook on the Bash tool
(`plugin/life-logistics/hooks/test-before-commit.sh`, wired up in
`.claude/settings.json`). Before any `git commit` it runs `uv run pytest` and
`ruff check`. If either fails, it exits with code 2, which means "block this
and show Claude the message", so Claude fixes the problem and tries again.
Commands that are not `git commit` pass straight through.

Use a hook when "usually" is not good enough. Use CLAUDE.md when it is.

## 4. Plugins: one installable package

A plugin bundles skills, hooks (and later commands, agents, MCP connections)
so you can install them in one step, on another computer or project, and update
them together. Ours lives in `plugin/life-logistics/`:

```
plugin/life-logistics/
  .claude-plugin/plugin.json   name, version, description
  skills/                      the four skills
  hooks/hooks.json             tells Claude Code which hook to run
  hooks/test-before-commit.sh  the hook itself
.claude-plugin/marketplace.json   makes this repo installable as a "marketplace"
```

To install it elsewhere, inside Claude Code:

```
/plugin marketplace add sieszwendamsie/life-logistics-planner
/plugin install life-logistics@life-logistics
```

Installed skills are namespaced, for example `/life-logistics:plan-next-stay`.
Honest limit: the skills call `uv run planner ...` and read `data/`, so they need
this repo checked out. The plugin carries the *workflow*; the Python tool stays
in the repo.

Inside this repo you do not need to install anything. `.claude/skills/` holds
symlinks to the plugin's skills, and `.claude/settings.json` wires the same hook,
so the repo and the plugin share one copy and cannot drift apart. (If you also
install the plugin here, the hook runs twice. Harmless, just slower.)

## 5. Where each thing goes

| You want to... | Use |
|---|---|
| Tell Claude a fact or rule for every session | `CLAUDE.md` |
| Teach a repeatable multi-step job | a skill |
| Guarantee something happens (tests, blocking) | a hook |
| Reach an outside service (calendar, drive) | an MCP connector |
| Share all of the above | a plugin |
| Keep personal, uncommitted preferences | `.claude/settings.local.json` (gitignored) |

## Try it

1. Ask Claude "plan the next stay" and watch it open `plan-next-stay`.
2. Break a test on purpose, ask Claude to commit, and watch the hook block it.
3. Open `plugin/life-logistics/skills/plan-year/SKILL.md` and change one rule.
   That is all it takes to change how Claude plans.

Next lessons worth doing: subagents (parallel helpers), and MCP connectors
(how Google Calendar is plugged in).
