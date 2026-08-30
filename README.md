# Fozzy's Puckline

NHL Elo ratings, win probabilities, and over/under predictions for every game on
the slate. Python computes; GitHub Actions runs it on a schedule; Cloudflare
Pages serves the result as a static site.

> Informational and educational. Not betting advice. No bets are placed, no
> accounts are connected, and no sportsbook is scraped.

## How it fits together

Predictions are a batch problem, not a request problem — the slate changes once
a day. So nothing here runs a server:

```
NHL public API
  └─ GitHub Actions (Python, cron)     ingest → rate → predict
       └─ data/raw/*.json.gz           immutable snapshots, replayable offline
       └─ data/games.parquet           normalized game table
            └─ web/public/data/v1/     versioned JSON contract, committed
                 └─ Cloudflare Pages   static React build
```

Every prediction the model has ever made stays in git history, which is what
makes the track record on `/model` auditable rather than a claim.

## Status

| Milestone | State |
| --------- | ----- |
| M0 scaffold | done |
| M1 ingest and backfill | done |
| M2 Elo engine and backtest | done |
| M3 totals model | done |
| M4 publish layer | next |
| M5 frontend | done |
| M6 automation | done |
| M7 Cloudflare deploy | config ready, needs the account connected |
| M8 track record and docs | done |

## Backend

```bash
cd backend
uv sync
uv run pytest
```

```bash
uv run puckline backfill --dry-run
```

Commands:

| Command | Does |
| ------- | ---- |
| `puckline backfill` | Rebuild the game table from the bulk season endpoint. ~25 requests for a decade. |
| `puckline ingest-day [DATE]` | Pull one league day of results. Defaults to yesterday. |
| `puckline stats` | Row counts per season, for eyeballing table health. |
| `puckline rate` | Current Elo ratings from the full game history. |
| `puckline backtest` | Score the current `params.json` walk-forward. |
| `puckline fit --write` | Re-fit Elo parameters on the validation window and save them. |
| `puckline calibrate-totals --write` | Measure the goal-model constants on the validation seasons. |
| `puckline backtest-totals` | Score the goal model and check the over/under gate. |
| `puckline ingest-schedule` | Pull upcoming games, with start times and venues. |
| `puckline publish` | Generate every JSON file the site reads. |

Backfill self-checks against known season totals. A clean run looks like this:

```
[ok ] 2015-16 reg   1230 parsed /  1230 claimed  (match)
[ok ] 2024-25 reg   1312 parsed /  1312 claimed  (match)
```

The left number is what we parsed, the right is what the API claimed it had. A
mismatch means the payload shape changed and the parser silently dropped rows.

## Frontend

```bash
cd web
npm install
npm run dev
```

Routes:

| Route | Shows |
| ----- | ----- |
| `/` | The slate. Win probability, fair moneyline, model total, P(over). |
| `/game/:date/:gameId` | One matchup in full, plus the result once graded. |
| `/ratings` | All 32 clubs, sortable, with the season Elo history. |
| `/team/:abbrev` | One club's rating curve. |
| `/model` | Methodology, calibration, and the running track record. |

The slate and matchup pages load eagerly; the three chart pages are split out,
because Recharts is larger than the rest of the app put together and the common
case is checking tonight's board on a phone. Initial load is ~84 KB gzipped.

## Automation

| Workflow | Trigger | Does |
| -------- | ------- | ---- |
| `ci.yml` | PR, push | ruff, mypy, pytest, contract tests, an idempotency check, and the web build. |
| `nightly.yml` | 11:00 UTC daily | Ingest results, pull the upcoming schedule, publish, commit. |
| `recalibrate.yml` | Mondays 12:00 UTC | Re-fit on the validation seasons; open a PR if anything moved. |
| `backfill.yml` | manual | Rebuild the game table from a chosen season. |

The latest puck drop is 10:30pm Pacific (05:30 UTC) and those games are final by
about 08:30 UTC, so an 11:00 UTC run clears the slate with margin every night.
Actions cron has no timezone support, so everything is UTC and stays correct
across both DST shifts.

Ingest and publish live in **one** workflow rather than two chained by
`workflow_run`. That is a deliberate departure from the original plan: chaining
adds a failure mode where the second job silently never fires, two jobs
committing to one branch can race, and each commit costs a Cloudflare Pages
build against a 500-a-month quota. One workflow means one commit per night and
no ordering to get wrong. Cadence is still one line of YAML.

Every step is idempotent. Publishing skips any file whose only change would be
the run timestamp, so a re-run, a late run, or a double run produces no diff at
all — CI enforces this, because without it the nightly job would commit every
night whether or not anything happened.

Recalibration never commits to `main`. It opens a pull request with the new
parameters and both backtests attached, because the model behind every published
prediction should change when someone decides it should.

## Opening-night checklist

**GitHub disables scheduled workflows after 60 days without repository
activity.** The NHL offseason is longer than that, so the schedules will switch
themselves off some time in August. That is intended — this site only runs in
season — but nothing will remind you to turn them back on.

Each October, before the first game:

1. Open the **Actions** tab and click **Enable workflow** on the banner.
2. Run `backfill.yml` via **Run workflow** to pick up the new season's schedule
   and carry ratings over.
3. Confirm the site shows the correct date on opening night.

## Deploying

Cloudflare Pages, connected to `main`. Root `web/`, build `npm run build`,
output `dist`. Caching, security headers, and the single-page-app fallback ship
with the build via `web/public/_headers` and `_redirects`.

Full runbook, including the R2 upgrade path for live scores:
[docs/DEPLOYING.md](docs/DEPLOYING.md).

## Data sources

| Source | Used for |
| ------ | -------- |
| `api-web.nhle.com/v1` | Daily schedule and results, including OT/SO outcome. |
| `api.nhle.com/stats/rest/en` | Bulk historical seasons and the team reference table. |

Both are undocumented and unofficial. Every response is snapshotted to
`data/raw/` before parsing, so a schema change costs a parser fix and a replay
rather than a re-crawl.

MoneyPuck is **not** used: its CSV endpoints redirect to a data license page.

## License

MIT. See [LICENSE](LICENSE).
