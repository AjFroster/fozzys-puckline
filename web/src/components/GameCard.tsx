import { Link } from "react-router-dom";
import type { SlateGame } from "../types/contract";
import { american, localTime, pct } from "../lib/format";
import { TeamMark } from "./TeamMark";
import { WinProbBar } from "./WinProbBar";

/**
 * One matchup. This is the product — everything else on the site is secondary
 * to getting this row right.
 */
export function GameCard({ game, date }: { game: SlateGame; date: string }) {
  const { prediction, result } = game;
  const overLine = prediction.totals.find((t) => t.line === prediction.fair_total_line);

  return (
    <Link
      to={`/game/${date}/${game.game_id}`}
      className="block rounded border border-ice-200 bg-white p-4 transition-colors hover:border-blade-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-rink-500 dark:border-ice-700 dark:bg-ice-800 dark:hover:border-blade-400"
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="tabular text-xs text-ice-400">
          {result ? "Final" : localTime(game.start_utc)}
          {result && result.last_period !== "REG" ? ` · ${result.last_period}` : ""}
        </span>
        {game.away.b2b || game.home.b2b ? (
          <span className="rounded-sm bg-ice-100 px-1.5 py-0.5 text-[10px] font-medium tracking-wide text-ice-400 uppercase dark:bg-ice-700">
            {game.away.b2b ? game.away.abbrev : game.home.abbrev} back-to-back
          </span>
        ) : null}
      </div>

      <div className="mt-3 space-y-2">
        <Side
          abbrev={game.away.abbrev}
          elo={game.away.elo}
          odds={prediction.away_ml_fair}
          score={result?.home_score !== undefined ? result.away_score : null}
          won={result ? !result.home_won : null}
        />
        <Side
          abbrev={game.home.abbrev}
          elo={game.home.elo}
          odds={prediction.home_ml_fair}
          score={result ? result.home_score : null}
          won={result ? result.home_won : null}
          home
        />
      </div>

      <div className="mt-3">
        <WinProbBar
          awayAbbrev={game.away.abbrev}
          homeAbbrev={game.home.abbrev}
          homeProb={prediction.home_win_prob}
        />
      </div>

      <div className="tabular mt-3 flex flex-wrap gap-x-4 gap-y-1 border-t border-ice-100 pt-3 text-xs text-ice-400 dark:border-ice-700">
        <span>
          Total <strong className="font-semibold text-ice-500 dark:text-ice-200">
            {prediction.exp_total.toFixed(2)}
          </strong>
        </span>
        <span>
          Line{" "}
          <strong className="font-semibold text-ice-500 dark:text-ice-200">
            {prediction.fair_total_line}
          </strong>
          {overLine ? ` · over ${pct(overLine.p_over)}` : ""}
        </span>
        {result ? (
          <span>
            Actual{" "}
            <strong className="font-semibold text-ice-500 dark:text-ice-200">
              {result.total_goals}
            </strong>
          </span>
        ) : null}
      </div>
    </Link>
  );
}

function Side({
  abbrev,
  elo,
  odds,
  score,
  won,
  home = false,
}: {
  abbrev: string;
  elo: number;
  odds: number;
  score: number | null;
  won: boolean | null;
  home?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div className="flex min-w-0 items-center gap-2">
        <TeamMark abbrev={abbrev} />
        {home ? <span className="text-xs text-ice-400">home</span> : null}
      </div>
      <div className="tabular flex items-center gap-4 text-sm">
        <span className="text-ice-400">{elo.toFixed(0)}</span>
        <span className="w-12 text-right text-ice-500 dark:text-ice-200">{american(odds)}</span>
        {score !== null ? (
          <span
            className={`w-5 text-right font-display text-xl font-bold ${
              won ? "text-ice-900 dark:text-ice-50" : "text-ice-300 dark:text-ice-500"
            }`}
          >
            {score}
          </span>
        ) : null}
      </div>
    </div>
  );
}
