/**
 * The JSON contract between the Python backend and this app.
 *
 * These types mirror the pydantic models that generate `public/data/v1/*.json`.
 * The path is versioned, so a breaking change ships as `/v2/` and this file
 * gains a sibling rather than being edited in place.
 */

export type GameState = "FUT" | "PRE" | "LIVE" | "OFF" | "FINAL";
export type LastPeriod = "REG" | "OT" | "SO";

export interface TeamSide {
  abbrev: string;
  elo: number;
  rest_days: number;
  b2b: boolean;
}

export interface TotalLine {
  /** The book line, e.g. 5.5 or 6.5. */
  line: number;
  p_over: number;
}

export interface Prediction {
  home_win_prob: number;
  away_win_prob: number;
  /** Fair American odds — no vig applied. Never a sportsbook price. */
  home_ml_fair: number;
  away_ml_fair: number;
  exp_goals_home: number;
  exp_goals_away: number;
  exp_total: number;
  /** The total at which p_over is 0.500. Book-independent. */
  fair_total_line: number;
  totals: TotalLine[];
}

export interface GameResult {
  home_score: number;
  away_score: number;
  last_period: LastPeriod;
  total_goals: number;
}

export interface SlateGame {
  game_id: number;
  start_utc: string;
  state: GameState;
  home: TeamSide;
  away: TeamSide;
  prediction: Prediction;
  /** Null until the next morning's grading job fills it in. */
  result: GameResult | null;
}

export interface Slate {
  schema: string;
  generated_at: string;
  model_version: string;
  date: string;
  games: SlateGame[];
}

export interface TeamRating {
  abbrev: string;
  name: string;
  elo: number;
  rank: number;
  percentile: number;
  elo_7d_change: number;
  /** Win probability against a league-average opponent on neutral ice. */
  win_prob_vs_average: number;
}

export interface Ratings {
  schema: string;
  generated_at: string;
  season: number;
  teams: TeamRating[];
}
