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

## Elo *(planned — M2)*

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
| `travel_penalty` | −10 max | Scaled by distance and time-zone change. Pregame only. |

In the backfill window, 22.4% of games go past regulation (2,193 OT and 1,063
shootout out of 14,508 finals). How those are credited is therefore not a detail.

## Totals and over/under *(planned — M3)*

Elo is unitless — it cannot produce a goal total. A second, independent
estimator handles that:

```
A_team = goals_for_per60     / league_mean    # attack multiplier
D_team = goals_against_per60 / league_mean    # defense multiplier

lam_home = L * A_home * D_away * home_goal_boost
lam_away = L * A_away * D_home
```

Rates are exponentially weighted with a ~20-game half-life and shrunk toward the
league mean, so early-season numbers are not wild. Regulation goals are Poisson;
the total is the convolution, solved in closed form.

Three things decide whether this is right or subtly wrong:

1. **Book totals settle including overtime and the shootout**, and a shootout
   winner is credited exactly one goal. Modelling regulation only and comparing
   to a book line is a silent, permanent bias. When regulation ends tied, add one
   goal; the probability of that tie comes from the Skellam of the two Poissons.
2. **Empty-net goals fatten the right tail.** Pure Poisson slightly
   under-predicts 8+ goal games. A negative binomial is fitted as an alternative
   and the backtest chooses.
3. **The Poisson pair implies its own win probability.** When it disagrees with
   Elo by more than 5 points, flag the game. Persistent disagreement is a bug
   signal, not noise.

Published per game: `exp_total`, `p_over` at 5.5 and 6.5, and `fair_total_line`
— the total where `p_over` is 0.500. That last number is book-independent and
more useful than either fixed line.

## Odds presentation

Probability to American odds: `p ≥ 0.5 → −100p/(1−p)`, otherwise `100(1−p)/p`.
Decimal is `1/p`.

All published odds are **fair, no-vig** and labelled as such. Nothing is
presented as a sportsbook price, and market lines are not ingested in v1.

## Evaluation *(planned — M8)*

| Metric | Target | Note |
| ------ | ------ | ---- |
| Log loss | 0.66–0.68 | Primary. Anything under 0.66 deserves suspicion of a leak. |
| Brier skill vs. home baseline | > 0 | Minimum bar. |
| Straight-up accuracy | 57–59% | Roughly the practical ceiling. 65% means a bug. |
| Calibration curve | 10 bins | Of games called 60%, do ~60% win? |
| Total goals MAE | 1.8–2.0 | |
| Over/under hit rate at the fair line | ~50% | Near 50% by construction — a strong self-check. |

Closing line value is the honest measure of edge, and it is unavailable until
market odds are ingested. That is deferred.

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
