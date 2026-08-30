/**
 * The JSON contract between the Python backend and this app.
 *
 * Mirrors the pydantic models in `backend/src/fozzys_puckline/contracts.py`,
 * which generate everything under `public/data/v1/`. A contract test checks the
 * two stay in step, so adding a field here without adding it there — or the
 * reverse — fails CI rather than surfacing as undefined at runtime.
 *
 * The path is versioned: a breaking change ships as `/v2/` and gains a sibling
 * rather than being edited in place.
 */

export type GameState = "FUT" | "PRE" | "LIVE" | "OFF" | "FINAL";
export type LastPeriod = "REG" | "OT" | "SO";

/** Fields every published document carries. */
export interface Document {
  schema: string;
  generated_at: string;
  /** Changes whenever the parameters do, so a prediction traces to its model. */
  model_version: string;
}

export interface TeamSide {
  abbrev: string;
  elo: number;
  rest_days: number | null;
  b2b: boolean;
}

export interface TotalLine {
  line: number;
  p_over: number;
}

export interface Prediction {
  home_win_prob: number;
  away_win_prob: number;
  /** Fair American odds — no vig. Never a sportsbook price. */
  home_ml_fair: number;
  away_ml_fair: number;
  home_decimal_fair: number;
  away_decimal_fair: number;
  exp_goals_home: number;
  exp_goals_away: number;
  exp_total: number;
  /**
   * The half-integer line closest to a coin flip.
   *
   * Not interpolated. Totals are integers, so p_over is a step function and no
   * line sits at exactly 0.500 — an interpolated 5.84 would name a number
   * nobody can bet that still pays out at 55%.
   */
  fair_total_line: number;
  /** p_over at fair_total_line, so the residual discreteness stays visible. */
  fair_line_p_over: number;
  totals: TotalLine[];
}

export interface GameResult {
  home_score: number;
  away_score: number;
  last_period: LastPeriod;
  total_goals: number;
  home_won: boolean;
}

export interface SlateGame {
  game_id: number;
  start_utc: string | null;
  state: GameState;
  venue: string | null;
  home: TeamSide;
  away: TeamSide;
  prediction: Prediction;
  /** Null until the grading job fills it in the next morning. */
  result: GameResult | null;
}

export interface Slate extends Document {
  date: string;
  games: SlateGame[];
}

export interface TeamRating {
  team_id: number;
  abbrev: string;
  name: string;
  /** Includes any between-season regression; the upcoming slate uses this. */
  elo: number;
  rank: number;
  percentile: number;
  /** Movement over the last seven days the league actually played. */
  elo_7d_change: number;
  /** Win probability against a league-average opponent on neutral ice. */
  win_prob_vs_average: number;
}

export interface Ratings extends Document {
  season: number;
  teams: TeamRating[];
}

export interface RatingPoint {
  date: string;
  /** Team abbreviation to rating, for that day. */
  elo: Record<string, number>;
}

export interface RatingHistory extends Document {
  season: number;
  points: RatingPoint[];
}

export interface Team {
  team_id: number;
  abbrev: string;
  name: string;
  logo: string;
}

export interface Teams extends Document {
  teams: Team[];
}

export interface CalibrationBin {
  lower: number;
  upper: number;
  count: number;
  mean_predicted: number;
  observed: number;
  z: number;
}

export interface WindowMetrics {
  label: string;
  seasons: number[];
  games: number;
  log_loss: number;
  baseline_log_loss: number;
  log_loss_skill: number;
  brier: number;
  brier_skill: number;
  accuracy: number;
  baseline_accuracy: number;
  worst_calibration_z: number;
  calibration_threshold: number;
  well_calibrated: boolean;
  calibration: CalibrationBin[];
}

export interface TotalsMetrics {
  label: string;
  games: number;
  over_under_hit_rate: number;
  model_claimed_rate: number;
  total_mae: number;
  mean_log_likelihood: number;
  modelled_tie_rate: number;
  actual_tie_rate: number;
}

export interface SeasonMetrics {
  season: number;
  games: number;
  log_loss: number;
  baseline_log_loss: number;
  accuracy: number;
}

/**
 * How the model has done over the most recently graded games.
 *
 * The season windows are the honest evaluation but they are historical. This is
 * the number someone opening the page mid-season actually wants.
 */
export interface RecentForm {
  games: number;
  since: string;
  through: string;
  log_loss: number;
  baseline_log_loss: number;
  accuracy: number;
  correct: number;
  over_under_hit_rate: number;
  total_mae: number;
}

export interface Metrics extends Document {
  holdout_season: number;
  recent: RecentForm | null;
  windows: WindowMetrics[];
  totals: TotalsMetrics[];
  by_season: SeasonMetrics[];
}

/** One game day in the season-to-date record. */
export interface TrackPoint {
  date: string;
  games_today: number;
  correct_today: number;

  games: number;
  correct: number;
  accuracy: number;
  log_loss: number;
  baseline_log_loss: number;
  brier: number;
  over_under_hit_rate: number;

  /** Trailing window, so a cold streak stays visible. Null until it fills. */
  rolling_accuracy: number | null;
  rolling_log_loss: number | null;
}

/** A game the model called confidently and got wrong. */
export interface NotableGame {
  date: string;
  game_id: number;
  winner: string;
  loser: string;
  probability_given_to_winner: number;
  score: string;
}

/**
 * The live scoreboard for the season in progress.
 *
 * Separate from Metrics on purpose. That is the historical evaluation — fixed
 * windows, a holdout. This answers a different question: not "is the model
 * sound" but "how is it doing right now".
 */
export interface SeasonTrack extends Document {
  season: number;
  complete: boolean;
  through: string | null;
  rolling_window: number;
  summary: TrackPoint | null;
  points: TrackPoint[];
  calibration: CalibrationBin[];
  worst_calibration_z: number;
  calibration_threshold: number;
  well_calibrated: boolean;
  biggest_misses: NotableGame[];
}

export interface IndexEntry {
  date: string;
  games: number;
}

export interface Index extends Document {
  /** Date `latest.json` points at — today if games, else the next game day. */
  latest_date: string | null;
  dates: IndexEntry[];
}
