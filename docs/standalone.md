# Using the planner without Claude

Claude is only needed for things that require a browser or judgement. Everything else
runs as plain commands, on your laptop or on a schedule in GitHub.

## What runs without Claude

| Task | Command |
|---|---|
| Read your calendars into `data/` | `uv run planner import-ics --ics Travel=URL ...` |
| Windows, options, scenarios | `uv run planner windows` / `options` / `scenarios` |
| Year plan | `uv run planner year --out out/year.html` |
| Flight times that can work + Ryanair links | `uv run planner routes --month 2027-02` |
| Live Ryanair fares inside those windows | `uv run planner fares --month 2027-02` |
| All pages in one go | `uv run planner build` (writes `out/site/index.html`) |

## One-time setup

1. `uv sync`, then copy `examples/*.yaml` to `data/` (gitignored).
2. In Google Calendar: Settings, your calendar, "Integrate calendar", copy
   **Secret address in iCal format**. Do this for Travel, Family, Important, Work and
   Holidays in Poland. These links are passwords: never commit them or paste them in chats.
3. Put them in your shell profile, one per line (`NAME=URL`):
   ```
   export PLANNER_ICS='Travel=https://calendar.google.com/...basic.ics
   Family=https://...
   Important=https://...
   Work=https://...
   Holidays in Poland=https://...'
   ```
   Files also work: `--ics Travel=travel.ics` (export from Google Calendar).
4. `uv run planner build`, then open `out/site/index.html`.

The importer uses the same rules as the `import-calendar` skill (tags `#PL #IT #UK`,
`#Martin #Paula #Basia #girls #all`, `#must #pref #flex`, `#shutdown`, `#holiday`,
"La Suite - non disponibile"). Events it cannot place, for example with no Who tag, are
printed as `NEEDS YOU:` lines and left out. Nothing is guessed. Tag them in the calendar.
Importing rewrites `data/constraints.yaml`, so comments in that file are not kept.

## On a schedule, on your phone

`.github/workflows/build-site.yml` rebuilds the pages every morning in GitHub Actions
and saves them as a downloadable artifact (only people with repo access can get it).
Add these repository secrets (Settings, Secrets and variables, Actions): `PLANNER_ICS`
(the block above), `PLANNER_CONSTRAINTS`, `PLANNER_ACCOMMODATION`, `PLANNER_OPTIONS`
(paste the contents of the three `data/` files). Run it by hand from the Actions tab.

Publishing as a normal web page: GitHub Pages on a private repo needs a paid plan, and a
public page would expose your plans. Private options: a paid plan, Cloudflare Pages with
Access, or just syncing `out/site/` to a phone-friendly folder (iCloud, Google Drive).
Not set up yet; pick one when you want it.

## What still needs Claude

- **Live flight times and prices.** The planner does not scrape airlines. Without Claude,
  use the links from `planner routes --month YYYY-MM` (Ryanair per-day fares), then type
  the chosen flight into `data/options.yaml` yourself. Options without checked flights
  show "Flight not checked yet".
- Asking about untagged calendar events and writing events back to Calendar after you
  approve a plan.
- Door-to-door timetables and car hire prices (Kayak, Trenitalia).

## Next steps (not done)

- Publish `out/site/` privately (see above).
- A `planner flights` helper using the Ryanair API with your approval.
