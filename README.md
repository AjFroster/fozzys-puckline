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
| M3 totals model | next |
| M4 publish layer | |
| M5 frontend | |
| M6 automation | |
| M7 Cloudflare deploy | |
| M8 track record and docs | |

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
| `puckline fit --write` | Re-fit parameters on the validation window and save them. |

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
