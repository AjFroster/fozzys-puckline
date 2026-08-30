import { Link, useParams } from "react-router-dom";
import { useSlate } from "../lib/api";
import type { SlateGame } from "../types/contract";
import { american, localTime, longDate, pct } from "../lib/format";
import { Card, Loading, PageTitle, Problem } from "../components/Chrome";
import { TeamMark } from "../components/TeamMark";
import { WinProbBar } from "../components/WinProbBar";

/**
 * The date is part of the route rather than looked up.
 *
 * A game id encodes its season and sequence but not its date, and slates are
 * keyed by date — so without it, finding one game would mean fetching slates
 * until it turned up. Whoever links here already knows the date.
 */
export default function GameDetail() {
  const { date = "", gameId = "" } = useParams();
  const slate = useSlate(date);
  const game = slate.data?.games.find((g) => g.game_id === Number(gameId));

  if (slate.loading) return <Loading label="Loading the matchup" />;
  if (slate.error) return <Problem>{slate.error}</Problem>;
  if (!game) return <Problem>That game is not on the {longDate(date)} slate.</Problem>;

  return <GameView game={game} date={date} />;
}

function GameView({ game, date }: { game: SlateGame; date: string }) {
  const p = game.prediction;
  const venue = game.venue ? ` · ${game.venue}` : "";

  return (
    <>
      <Link
        to="/"
        className="mb-4 inline-block text-sm text-blade-500 hover:underline dark:text-blade-400"
      >
        ← Slate
      </Link>

      <PageTitle sub={`${longDate(date)} · ${localTime(game.start_utc)}${venue}`}>
        {game.away.abbrev} @ {game.home.abbrev}
      </PageTitle>

      <Card className="p-5">
        <div className="grid gap-6 sm:grid-cols-2">
          <SideBlock
            label="Away"
            abbrev={game.away.abbrev}
            elo={game.away.elo}
            odds={p.away_ml_fair}
            decimal={p.away_decimal_fair}
            prob={p.away_win_prob}
            goals={p.exp_goals_away}
            rest={game.away.rest_days}
            b2b={game.away.b2b}
            score={game.result ? game.result.away_score : null}
          />
          <SideBlock
            label="Home"
            abbrev={game.home.abbrev}
            elo={game.home.elo}
            odds={p.home_ml_fair}
            decimal={p.home_decimal_fair}
            prob={p.home_win_prob}
            goals={p.exp_goals_home}
            rest={game.home.rest_days}
            b2b={game.home.b2b}
            score={game.result ? game.result.home_score : null}
          />
        </div>

        <div className="mt-6">
          <WinProbBar
            awayAbbrev={game.away.abbrev}
            homeAbbrev={game.home.abbrev}
            homeProb={p.home_win_prob}
          />
        </div>

        {game.result ? (
          <p className="tabular mt-5 border-t border-ice-100 pt-4 text-sm text-ice-400 dark:border-ice-700">
            Final{game.result.last_period !== "REG" ? ` in ${game.result.last_period}` : ""} ·{" "}
            {game.result.total_goals} total goals · the model gave the winner{" "}
            <strong className="font-semibold text-ice-500 dark:text-ice-200">
              {pct(game.result.home_won ? p.home_win_prob : p.away_win_prob)}
            </strong>
          </p>
        ) : null}
      </Card>

      <h2 className="mt-8 mb-3 font-display text-xl font-semibold tracking-wide uppercase">
        Total goals
      </h2>
      <Card className="p-5">
        <dl className="tabular grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Stat label="Expected total" value={p.exp_total.toFixed(2)} />
          <Stat label="Fair line" value={String(p.fair_total_line)} />
          <Stat label="Over at fair line" value={pct(p.fair_line_p_over)} />
          {game.result ? <Stat label="Actual" value={String(game.result.total_goals)} /> : null}
        </dl>

        <div className="mt-5 overflow-x-auto">
          <table className="tabular w-full min-w-72 text-sm">
            <thead>
              <tr className="border-b border-ice-200 text-left text-xs tracking-wide text-ice-400 uppercase dark:border-ice-700">
                <th scope="col" className="pb-2 font-medium">Line</th>
                <th scope="col" className="pb-2 text-right font-medium">Over</th>
                <th scope="col" className="pb-2 text-right font-medium">Under</th>
              </tr>
            </thead>
            <tbody>
              {p.totals.map((t) => (
                <tr
                  key={t.line}
                  className="border-b border-ice-100 last:border-0 dark:border-ice-700/60"
                >
                  <td className="py-2">{t.line}</td>
                  <td className="py-2 text-right">{pct(t.p_over)}</td>
                  <td className="py-2 text-right">{pct(1 - t.p_over)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <p className="mt-4 text-xs text-ice-400">
          The fair line is the half-integer closest to a coin flip, not an interpolated value.
          Totals are whole numbers, so no line sits at exactly 50%.
        </p>
      </Card>
    </>
  );
}

function SideBlock({
  label,
  abbrev,
  elo,
  odds,
  decimal,
  prob,
  goals,
  rest,
  b2b,
  score,
}: {
  label: string;
  abbrev: string;
  elo: number;
  odds: number;
  decimal: number;
  prob: number;
  goals: number;
  rest: number | null;
  b2b: boolean;
  score: number | null;
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <Link
          to={`/team/${abbrev}`}
          className="hover:text-blade-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-rink-500 dark:hover:text-blade-400"
        >
          <TeamMark abbrev={abbrev} size={36} />
        </Link>
        {score !== null ? <span className="font-display text-3xl font-bold">{score}</span> : null}
      </div>
      <p className="mt-1 text-xs tracking-wide text-ice-400 uppercase">{label}</p>
      <dl className="tabular mt-4 grid grid-cols-2 gap-3">
        <Stat label="Win" value={pct(prob)} />
        <Stat label="Fair odds" value={`${american(odds)} · ${decimal.toFixed(2)}`} />
        <Stat label="Elo" value={elo.toFixed(1)} />
        <Stat label="Expected goals" value={goals.toFixed(2)} />
        <Stat label="Rest" value={rest === null ? "—" : `${rest}d`} />
        <Stat label="Back-to-back" value={b2b ? "Yes" : "No"} />
      </dl>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs tracking-wide text-ice-400 uppercase">{label}</dt>
      <dd className="mt-0.5 font-medium text-ice-900 dark:text-ice-50">{value}</dd>
    </div>
  );
}
