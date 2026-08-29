# Build plan

## The decision everything else follows from

Cloudflare's edge runtime is JavaScript-first, and Python Workers are heavy and
immature. Rather than fight that, note that predictions are a **batch problem**:
the slate changes once a day, so Python never has to serve a request.

GitHub Actions is therefore the compute layer. Python runs there on cron, writes
versioned JSON into the repo, and Cloudflare Pages serves a static React app
that reads it. No server, no database to operate, no cold starts, and every
prediction stays permanently auditable in git history.

## Locked decisions

| Question | Answer | Consequence |
| -------- | ------ | ----------- |
| Name | Fozzy's Puckline (`fozzys-puckline`) | |
| Visibility | Public | Free unlimited Actions minutes, which matters at several jobs per game day. |
| Backfill | 2015-16 forward | ~14,000 games. Modern sport, small sample — so five free parameters, and the COVID seasons are flagged. |
| Serving | Pages only; R2 deferred | One build per game day. No in-game live scores in v1. |
| Market odds | Deferred | No third-party key to manage. Cannot yet measure edge vs. market. |
| Offseason | In-season only, no keepalive | Schedules go dormant in August. Re-enabling each October is manual. |

## Milestones

| # | Deliverable | Done when |
| - | ----------- | --------- |
| M0 | Scaffold | `uv run pytest` and `npm run build` pass in CI. **Done.** |
| M1 | Ingest and backfill | Backfill produces exactly 1312 regular-season games for 2024-25, matching the API's own count. **Done** — all ten reference seasons matched. |
| M2 | Elo engine and backtest | Log loss beats the always-home baseline on a held-out season, calibration within ±3 points across all ten bins. |
| M3 | Totals model | Over/under hit rate at the model's own fair line falls in 48–52% on the held-out season. |
| M4 | Publish layer | A full day of JSON validates against the schema and round-trips through the frontend's TypeScript types. |
| M5 | Frontend | Slate, ratings, and model pages render from real data on a 390px viewport. |
| M6 | Automation | Two consecutive nights run unattended; a deliberate double-run produces a byte-identical commit. |
| M7 | Cloudflare | Live on the custom domain, reflecting a bot commit within ten minutes. |
| M8 | Track record | The model page shows real graded results for the season to date, including the losses. |

## Workflows

| Workflow | Trigger | Does |
| -------- | ------- | ---- |
| `ci.yml` | PR, push | ruff, mypy, pytest, contract tests, `npm run build`. **Done.** |
| `ingest-results.yml` | cron 11:00 UTC | Yesterday's finals → game table → Elo update → grade yesterday's predictions → commit. |
| `predict-slate.yml` | `workflow_run` after ingest | Schedule for today + 7 days, score every matchup, publish JSON, commit. |
| `recalibrate.yml` | cron Mon 12:00 UTC | Re-fit parameters; open a PR if they shifted materially. |
| `backfill.yml` | manual dispatch | Rebuild from a chosen start season. |

The latest NHL puck drop is 10:30pm Pacific (05:30 UTC), and those games are
final by roughly 08:30 UTC. An 11:00 UTC ingest clears the slate with margin
every night of the year without any timezone logic — Actions cron has no
timezone support, so everything is UTC and stays correct across both DST shifts.

### Operational rules

- **Idempotency.** Cron can fire 5–30 minutes late or skip entirely. Every job
  recomputes its full output for a date range rather than appending deltas, so a
  re-run or a missed run self-heals.
- **One `concurrency` group per workflow**, plus `git pull --rebase` with one
  retry before push.
- **Rate limiting.** Exponential backoff with full jitter, ETag conditional
  requests, and a hard request budget per process.
- **Schema drift.** Contract tests run against stored raw snapshots. A parse
  failure opens an issue rather than publishing a stale site silently.

## Hosting

v1 is Cloudflare Pages with git integration on `main`: root `web/`, build
`npm run build`, output `dist`. A `_headers` file caches `/data/*` for five
minutes at the edge.

The free tier allows **500 builds per month**. One data commit per game day is
30–60 builds — comfortable. A 30-minute live-refresh loop would push ~480 on its
own and blow the quota, which is why in-game scores are out of v1.

**The v2 upgrade:** Actions writes fast-changing JSON straight to an R2 bucket, a
Worker serves it at `/api/*`, and a Pages path filter limits builds to code
changes. The frontend fetches a URL and does not care what is behind it, so this
is a config change and one base-URL constant — not a rewrite.

## JSON contract

Versioned under `/v1/` so the frontend can pin. Pydantic generates it; contract
tests verify the shape on every commit; `web/src/types/contract.ts` mirrors it.

```
web/public/data/v1/
├── index.json              available dates, schema version, build stamp
├── latest.json             today's slate — what the homepage fetches
├── slate/YYYY-MM-DD.json   one per day, permanent archive
├── ratings/current.json
├── ratings/history.json    date x team Elo, for the chart
├── teams.json              ids, abbrevs, colors, divisions, venue coords
└── metrics.json            calibration and track record
```

## Risks

| Risk | Likelihood | Mitigation |
| ---- | ---------- | ---------- |
| Schedules disabled after the offseason and not turned back on | Certain | Accepted; site is in-season only. README opening-night checklist, since GitHub gives no notification. |
| Overfitting the parameter sweep | High | Raised by the 14,000-game window. Five free parameters, strict walk-forward, untouched holdout, published live calibration. |
| NHL API changes shape | Medium | Raw snapshots make history replayable offline; contract tests open an issue on drift. |
| Pages build quota exceeded | Medium | Daily commits only in v1; R2 + Worker before any high-frequency refresh. |
| Anomalous 2019-20 / 2020-21 seasons skew the fit | Medium | Crowd, schedule, and neutral-site flags at ingest; no-crowd games excluded from the home-ice fit. |
| Model looks unimpressive | Certain | A property of the sport, not a bug. Framed by publishing log loss against the baseline, not a hero accuracy number. |
| Gambling framing | Low | Informational only. No bet placement, no accounts, no affiliate links, no sportsbook scraping. |

See [METHODOLOGY.md](METHODOLOGY.md) for the model specifications.
