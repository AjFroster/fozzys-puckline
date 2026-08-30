import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useRatingHistory, useRatings, useTeams } from "../lib/api";
import { pct, seasonLabel, shortDate, signed } from "../lib/format";
import { Card, Loading, PageTitle, Problem } from "../components/Chrome";
import { TeamMark } from "../components/TeamMark";

export default function TeamPage() {
  const { abbrev = "" } = useParams();
  const ratings = useRatings();
  const history = useRatingHistory();
  const teams = useTeams();

  const team = ratings.data?.teams.find((t) => t.abbrev === abbrev);
  const name = teams.data?.teams.find((t) => t.abbrev === abbrev)?.name ?? abbrev;

  const series = useMemo(
    () =>
      (history.data?.points ?? [])
        .filter((point) => abbrev in point.elo)
        .map((point) => ({ date: point.date, elo: point.elo[abbrev] })),
    [history.data, abbrev],
  );

  if (ratings.loading) return <Loading label="Loading the club" />;
  if (ratings.error) return <Problem>{ratings.error}</Problem>;
  if (!team) return <Problem>No club with the code {abbrev}.</Problem>;

  const peak = series.reduce((best, p) => Math.max(best, p.elo ?? 0), 0);
  const trough = series.reduce((worst, p) => Math.min(worst, p.elo ?? Infinity), Infinity);

  return (
    <>
      <Link
        to="/ratings"
        className="mb-4 inline-block text-sm text-blade-500 hover:underline dark:text-blade-400"
      >
        ← Ratings
      </Link>

      <div className="mb-2 flex items-center gap-3">
        <TeamMark abbrev={abbrev} size={44} />
      </div>
      <PageTitle sub={ratings.data ? seasonLabel(ratings.data.season) : undefined}>
        {name}
      </PageTitle>

      <Card className="p-5">
        <dl className="tabular grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Stat label="Elo" value={team.elo.toFixed(1)} />
          <Stat label="Rank" value={`${team.rank} of 32`} />
          <Stat label="vs average" value={pct(team.win_prob_vs_average)} />
          <Stat
            label="Last 7 days"
            value={team.elo_7d_change === 0 ? "—" : signed(team.elo_7d_change)}
          />
        </dl>
      </Card>

      <h2 className="mt-8 mb-3 font-display text-xl font-semibold tracking-wide uppercase">
        Rating curve
      </h2>
      <Card className="p-4">
        <div className="h-64 w-full">
          {series.length === 0 ? (
            <p className="py-16 text-center text-sm text-ice-400">No history for this club yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={series} margin={{ top: 4, right: 8, bottom: 4, left: -16 }}>
                <CartesianGrid
                  stroke="currentColor"
                  className="text-ice-200 dark:text-ice-700"
                  strokeDasharray="2 4"
                  vertical={false}
                />
                <XAxis
                  dataKey="date"
                  tickFormatter={shortDate}
                  minTickGap={48}
                  tick={{ fontSize: 11 }}
                  stroke="currentColor"
                  className="text-ice-400"
                />
                <YAxis
                  domain={["dataMin - 15", "dataMax + 15"]}
                  tick={{ fontSize: 11 }}
                  width={64}
                  stroke="currentColor"
                  className="text-ice-400"
                />
                <Tooltip
                  formatter={(value) => [
                    (typeof value === "number" ? value : Number(value) || 0).toFixed(1),
                    "Elo",
                  ]}
                  labelFormatter={(label) => (typeof label === "string" ? shortDate(label) : "")}
                  contentStyle={{ fontSize: 12, borderRadius: 4 }}
                />
                <Line
                  type="monotone"
                  dataKey="elo"
                  dot={false}
                  isAnimationActive={false}
                  stroke="currentColor"
                  className="text-rink-500 dark:text-rink-400"
                  strokeWidth={2}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
        {series.length > 0 ? (
          <p className="tabular mt-3 text-xs text-ice-400">
            Season high {peak.toFixed(1)} · low {trough.toFixed(1)} · {series.length} rated days
          </p>
        ) : null}
      </Card>
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs tracking-wide text-ice-400 uppercase">{label}</dt>
      <dd className="mt-0.5 text-lg font-medium text-ice-900 dark:text-ice-50">{value}</dd>
    </div>
  );
}
