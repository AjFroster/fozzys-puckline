# Methodology

What the model does, what it is fitted on, and what it deliberately ignores.
Sections marked *planned* are specified but not yet implemented.

## Scope of the data

Backfill runs from **2015-16 forward** — roughly 14,000 regular-season games
plus playoffs. That window is the tightest match to the modern sport, and it is
the smallest of the options considered. Two consequences follow.

### Two seasons inside the window are not normal hockey

| Season | What was different |
| ------ | ------------------ |
| 2019-20 | Paused 2020-03-11. The regular season had crowds; the restart from 2020-08-01 was a neutral-site, no-crowd bubble. |
| 2020-21 | 56 games, four temporary divisions with no cross-division play, and overwhelmingly empty buildings. |

Every game carries `no_fans`, `neutral_site`, and `divisional_only` flags,
applied at ingest by `seasons.season_flags`.

Empty buildings suppress home advantage. Measured over the backfill window:

| Split | Home win rate | Games |
| ----- | ------------- | ----- |
| Crowd present | 53.96% | 13,426 |
| No crowd | 52.50% | 1,082 |

Roughly half the edge, not none of it. A 1.5-point bias is still large at this
sample size, so `no_fans` games are excluded from the home-ice fit rather than
averaged in.

The 2020-21 divisional-only schedule also starves the model of cross-division
information. Inter-division rating comparisons from that season are lower
confidence, and should not be treated as if the pool were uniform.

### The sample is small enough that overfitting is the main risk

The parameter search is capped at **five free parameters** — `K`, `HFA`, the
OT/SO credit, the season carryover, and one margin-of-victory constant.
Everything else stays at its default. A ten-parameter sweep over 14,000
high-variance games will find beautiful noise.

Fitting is strictly walk-forward: every game is predicted using only ratings
that existed before it, and the most recent full season is held out untouched
until parameters are frozen.

## Elo

```
diff   = R_home + HFA + adj_home - R_away - adj_away
E_home = 1 / (1 + 10 ** (-diff / 400))

mov = log(abs(goal_diff) + 1) * (2.05 / (0.001 * diff_winner + 2.05))

R_home += K * mov * (S_home - E_home)
R_away -= K * mov * (S_home - E_home)
```

| Parameter | Start | Rationale |
| --------- | ----- | --------- |
| `K` | 6.0 | 82 games is many updates. Low `K` keeps ratings stable in a high-variance sport. |
| `HFA` | 35 | ~54% home win rate is roughly 30–40 Elo points. Fitted, not hardcoded — it has drifted for a decade. |
| `S` for OT/SO win | 0.65 / 0.35 | A 3-on-3 overtime or shootout is close to a coin flip. Full credit teaches the model something false. |
| `carryover` | 0.70 | Between seasons, `R = 0.70·R + 0.30·1505`. Rosters turn over. |
| `b2b_penalty` | −25 | Applied to the pregame difference, **not** the stored rating. A tired team is temporarily worse, not permanently worse. |
| `travel_penalty` | not implemented | Needs venue coordinates, which the current endpoints do not provide. Deliberately absent rather than guessed. |

### Fitted values

Coordinate descent on validation log loss, five free axes, holdout never touched:

| Parameter | Default | Fitted |
| --------- | ------- | ------ |
| `k` | 6.0 | **8.0** |
| `hfa` | 35.0 | **25.0** |
| `ot_credit` | 0.65 | 0.65 |
| `carryover` | 0.70 | **0.75** |
| `diff_scale` | 1.0 | 1.0 |

`hfa` fitting to 25 rather than 35 is the drift the plan predicted: home ice is
worth less than it used to be.

`diff_scale` landing exactly at 1.0 is the useful negative result — the Elo
400-point scale needs no correction, so the model is neither systematically
over- nor under-confident.

### Team identity

Team ids are not stable. Within this window one club changes id twice:
`ARI 53` (through 2023-24) → `UTA Hockey Club 59` (2024-25) → `UTA Mammoth 68`
(2025-26 on). 53 and 59 sit in *different* franchises, so no field in the API
links them — the Coyotes' franchise was deactivated and Utah was issued a new
one, even though the roster moved across intact.

All three resolve to one rating history, because ratings model on-ice continuity
rather than legal identity. Without that map Utah resets to an expansion rating
twice, once inside the holdout season. Vegas and Seattle are genuinely new and
do start at `expansion_init`.

### Why `mov_const` is pinned rather than fitted

Given the axis, the search walks it to the edge of the grid for a gain in the
fifth decimal:

| `mov_const` | validation | holdout |
| ----------- | ---------- | ------- |
| 2.05 | 0.66346 | **0.68864** |
| 4.0 | 0.66337 | 0.68936 |
| 100 | 0.66338 | 0.69027 |

Validation is flat; holdout degrades monotonically. That is the noise floor of
14,000 games being mistaken for signal. The fitting loop now requires a minimum
improvement of 1e-4 before it will move any parameter, and `mov_const` is held
at 2.05.

In the backfill window, 22.4% of games go past regulation (2,193 OT and 1,063
shootout out of 14,508 finals). How those are credited is therefore not a detail.

## Totals and over/under

Elo is unitless and cannot produce a goal total, so this is a second, independent
estimator. Most of what the original plan specified for it turned out to be wrong
once measured against the data; what follows is what the data actually supports.

### Regulation scores are exactly recoverable

Book totals settle on the **final** score including overtime and the shootout,
and a shootout winner is credited exactly one goal. But rates must be estimated
on *regulation* goals — learning from final scores folds the overtime goal into
every team's attack rate and inflates every total the model publishes.

Both are available. Reaching overtime requires regulation to have been tied, and
the winner is credited exactly one goal, so removing that goal reconstructs
regulation without ambiguity. Verified across all 14,508 finals in the backfill:
every reconstruction comes out tied, none goes negative.

### The rate model

```
attack  = (ewma_goals_for     + prior * league) / ((weight + prior) * league)
defense = (ewma_goals_against + prior * league) / ((weight + prior) * league)

lam_home = 2 * league *      home_share  * attack_home * defense_away
lam_away = 2 * league * (1 - home_share) * attack_away * defense_home
```

Exponentially weighted with a 30-game half-life, shrunk toward league average by
a 30-game prior. **A team ages only on its own games.** Ageing every team on
every league game applies the half-life about sixteen times too fast — a team
plays 82 of the season's 1,312 games — which collapsed every multiplier onto the
prior and left predicted totals with a standard deviation of 0.04 goals across
all matchups. That bug made the model produce essentially one number for every
game.

### Totals are under-dispersed, so the negative binomial is the wrong family

The plan called for a negative binomial to model a fat right tail from empty-net
goals. The data says the opposite: final totals have **variance 5.29 against a
mean 6.00**, a ratio of 0.88. That is under-dispersion, and a negative binomial
can only ever *add* variance — reaching for it would move the model further from
the data.

The model uses a **Conway-Maxwell-Poisson** shape instead, which handles both
directions. The fitted value is 1.162, where 1.0 would be exactly Poisson.

This is not cosmetic. Excess spread in a right-skewed distribution drags the
median below the mean, and the median is what sets the published line.

### The tie correction

The final total is the regulation total plus one goal when regulation ended
tied, so `P(tie)` matters directly. Independent Poisson is badly wrong about it,
and about the margin generally:

| Regulation margin | Observed | Independent Poisson |
| ----------------- | -------- | ------------------- |
| 0 (tie) | 22.4% | 16.9% |
| 1 | 19.6% | 30.8% |
| 3 | 22.7% | 14.8% |

Empty-net goals push one-goal games out to two and three, and pulled-goalie
pressure pushes others back to a tie. Both drain the same bucket, and an
independence assumption cannot express either.

So `P(tie | regulation total)` is modelled directly rather than derived from a
joint. The excess over the binomial baseline is close to linear in the total once
expressed in log odds — measured at +18.4 points at a total of 2, decaying to
+1.2 points at 10 — which is what the two tie parameters describe.

The slope is fitted by weighted least squares, and then **the intercept is solved
so the model's marginal tie rate matches the observed one.** Least squares in log
odds does not preserve the aggregate; left alone it understated the marginal by
about two points, and since every tie adds exactly one goal, that landed directly
on every published total as a level bias.

### The fair line is a real half-integer

The plan's JSON contract specified a continuous `fair_total_line` such as 6.1.
That is not a well-defined quantity. Totals are integers, so `p_over` is a step
function: for a Poisson(6) total, `p_over(5.5)` is 0.554 and `p_over(6.5)` is
0.394, with nothing in between. Interpolating those to 5.84 produces a number
nobody can bet which does not have the property it claims — as an actual line,
5.84 still resolves every total of 6 as an over, so it pays at 55.4%, not 50%.

`fair_total_line` is therefore the half-integer line closest to a coin flip, and
`fair_line_p_over` is published beside it so the residual discreteness is visible
rather than implied away.

### What is not shipped

The plan called for cross-checking the Elo win probability against the one
implied by the goal model, flagging disagreements over 5 points. **That check is
not shipped.** Independent Poisson misprices the regulation margin by up to 11
points, so the flag would fire constantly on the goal model's own defect rather
than on any real disagreement — worse than having no check at all.

### Estimation discipline

`league_goals`, `home_share`, `dispersion`, and the two tie parameters are
**measured** on the validation seasons, not fitted. Only `half_life`,
`prior_games`, and `carryover` are searched.

That split is not academic. When `tie_intercept` was inside the likelihood sweep
it moved from a measured 0.64 to 0.50 and made the published over/under
measurably worse — the likelihood was happy to buy distribution-shape fit with a
quantity that can be measured precisely on its own.

An earlier pass estimated these constants on the **full** backfill, holdout
included. That is a leak, and it invalidated the holdout regardless of the
result. The constants differ materially once corrected — the tie intercept was
0.93 on the full window against 0.64 on validation only.

### Results

| Window | n | O/U at fair line | Model claims | Deviation | Total MAE |
| ------ | - | ---------------- | ------------ | --------- | --------- |
| Validation | 8,469 | 0.5076 | 0.4981 | 1.74σ | 1.845 |
| Holdout 2025-26 | 1,312 | 0.5183 | 0.5004 | 1.29σ | 1.845 |

Both inside the 48–52% gate, and neither deviation is significant.

A residual level bias remains: the model under-predicts the mean total by 0.04
goals on validation and 0.10 on the holdout. On the holdout that is almost
entirely the tie rate — 2025-26 sent **24.85%** of games past regulation against
the model's 21.8%, the highest rate in the window. The model estimates a single
league-wide tie rate and cannot anticipate a season being unusually prone to
overtime, which is a real limitation rather than a tuning error.

## Odds presentation

Probability to American odds: `p ≥ 0.5 → −100p/(1−p)`, otherwise `100(1−p)/p`.
Decimal is `1/p`.

All published odds are **fair, no-vig** and labelled as such. Nothing is
presented as a sportsbook price, and market lines are not ingested in v1.

## Evaluation

Walk-forward, holdout untouched by fitting. Warmup is the first three seasons;
validation is 2018-19 through 2024-25; holdout is 2025-26.

### Results

| Window | n | Log loss | Baseline | Skill | Accuracy | Worst bin |
| ------ | - | -------- | -------- | ----- | -------- | --------- |
| Validation | 7,601 | 0.66346 | 0.69008 | +3.86% | 59.9% | 0.94σ |
| Holdout 2025-26 | 1,312 | 0.68867 | 0.69217 | +0.51% | 53.1% | 2.56σ |

The model beats the baseline in **every** season in the window. But the holdout
is far weaker than validation, and that is worth being precise about rather than
averaging away.

### Why the holdout is the hardest season in the window

It is not overfitting: the *untuned default* parameters degrade on 2025-26 by
the same amount (0.68912, skill +0.44%). Three properties of that season:

| | 2025-26 | Prior three seasons |
| - | ------- | ------------------- |
| Mid-season break | 20 days (2026-02-05 to 02-25, Olympics) | none |
| Past-regulation rate | 24.96% (window high) | 20.6–23.2% |
| Home win rate | 52.21% (window low) | 52.4–56.3% |

A quarter of games decided past regulation, and the weakest home ice on record,
is a season with more coin flips in it. Holding it out is conservative, not
flattering — but the honest reading is that a single season is a noisy test, and
the +0.51% skill there should not be quoted as *the* number without the
per-season table beside it.

### The calibration gate, and why it was respecified

The original gate was "within ±3 points across all ten bins". That test is not
meaningful at this sample size:

- 2017-18 shows an 11.5-point gap in a bin holding 30 games. Two standard errors
  there is 17.9 points, so the gap is unremarkable noise — but a fixed
  points threshold flags it.
- Pooled validation shows a 4.5-point gap in a bin holding 1,790 games, which is
  3.9 standard errors and a genuine miss — and a ±3-point-per-bin reading
  across single seasons would never reliably surface it.

The gate is now **the gap in standard errors**, with a Bonferroni correction for
the number of populated bins tested. Every bin is a separate test, so comparing
each against a flat 2σ line asks the model to pass five coin flips at once: a
perfectly calibrated model fails that roughly 21% of the time.

Under the corrected gate, validation passes comfortably (0.94σ against a 2.64σ
threshold) and the holdout passes **marginally** — 2.56σ against 2.576σ. That is
a pass by 0.02σ, which is to say it is at the line rather than clear of it.

### Still to come

| Metric | Target | Status |
| ------ | ------ | ------ |
| Total goals MAE | 1.8–2.0 | M3 |
| Over/under hit rate at the fair line | ~50% | M3 |
| Closing line value | — | Needs market odds; deferred |

## The published track record

Two views, answering two different questions.

`/model` is the historical evaluation, from `metrics.json`: fixed windows, fitted
parameters, a holdout season. It answers *is the model sound*.

`/track` is the live scoreboard for the season in progress, from `track.json`.
It answers *how is it doing right now* — a point per game day carrying the
running record, the trailing 100-game window, and the season's calibration. The
tracked season is simply the most recent one with a finished game, so it rolls
over on its own the first night of a new season.

Both show a rolling window rather than a chosen one, and both name losses. The
`/track` page lists the games the model was most confident about and still got
wrong, because a record that only shows the aggregate is easy to read as better
than it is.

Three things are deliberately shown rather than smoothed over: the holdout is
much weaker than validation, the per-season chart makes that visible, and the
page says plainly that a season of 1,312 games is a noisy test.

## Known gaps

- **Starting goalie is not modelled.** This is the largest single missing
  factor. It needs a reliable pre-game lineup source, which the current
  endpoints do not give with enough lead time.
- **Injuries are not modelled.**
- **Playoff series probabilities** are not computed.
- Playoff game counts in the raw data are *scheduled slots*, not games played —
  a sweep still lists games 5 through 7. Those placeholders stay in a future
  state permanently and are filtered by `Game.is_final`.
- 2020-21 `no_fans` is a slight over-count: a few teams admitted limited crowds
  late in that season, which is not modelled.
