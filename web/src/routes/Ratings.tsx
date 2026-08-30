import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useRatingHistory, useRatings } from "../lib/api";
import type { TeamRating } from "../types/contract";
import { pct, seasonLabel, shortDate, signed } from "../lib/format";
import { Card, Loading, PageTitle, Problem, Provenance } from "../components/Chrome";
import { TeamMark } from "../components/TeamMark";

type SortKey = "rank" | "abbrev" | "elo_7d_change" | "win_prob_vs_average";

export default function RatingsPage() {
  const ratings = useRatings();
  const history = useRatingHistory();
  const [sort, setSort] = useState<SortKey>("rank");
  const [descending, setDescending] = useState(false);
  const [highlight, setHighlight] = useState<string | null>(null);

  const rows = useMemo(() => {
    const teams = [...(ratings.data?.teams ?? [])];
    teams.sort((a, b) => compare(a, b, sort));
    return descending ? teams.reverse() : teams;
  }, [ratings.data, sort, descending]);

  const chart = useMemo(() => {
    const points = history.data?.points ?? [];
    // Recharts wants one row per x value with a key per series.
    return points.map((point) => ({ date: point.date, ...point.elo }));
  }, [history.data]);

  const abbrevs = useMemo(
    () => (ratings.data?.teams ?? []).map((t) => t.abbrev),
    [ratings.data],
  );

  if (ratings.loading) return <Loading label="Loading ratings" />;
  if (ratings.error) return <Problem>{ratings.error}</Problem>;
  if (!ratings.data) return <Problem>No ratings published yet.</Problem>;

  return (
    <>
      <PageTitle sub={`${seasonLabel(ratings.data.season)} · all 32 clubs`}>Elo ratings</PageTitle>

      <Card className="mb-8 p-4">
        <div className="mb-2 flex items-baseline justify-between">
          <h2 className="font-display text-lg font-semibold tracking-wide uppercase">
            Season history
          </h2>
          <span className="text-xs text-ice-400">
            {highlight ? `Showing ${highlight}` : "Hover a line"}
          </span>
        </div>
        <div className="h-72 w-full">
          {chart.length === 0 ? (
            <p className="py-16 text-center text-sm text-ice-400">No history published yet.</p>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chart} margin={{ top: 4, right: 8, bottom: 4, left: -16 }}>
                <CartesianGrid stroke="currentColor" className="text-ice-200 dark:text-ice-700" strokeDasharray="2 4" vertical={false} />
                <XAxis
                  dataKey="date"
                  tickFormatter={shortDate}
                  minTickGap={48}
                  tick={{ fontSize: 11 }}
                  stroke="currentColor"
                  className="text-ice-400"
                />
                <YAxis
                  domain={["dataMin - 20", "dataMax + 20"]}
                  tick={{ fontSize: 11 }}
                  width={64}
                  stroke="currentColor"
                  className="text-ice-400"
                />
                <Tooltip content={<HistoryTooltip highlight={highlight} />} />
                {abbrevs.map((abbrev) => (
                  <Line
                    key={abbrev}
                    type="monotone"
                    dataKey={abbrev}
                    dot={false}
                    isAnimationActive={false}
                    stroke="currentColor"
                    className={
                      highlight === abbrev
                        ? "text-rink-500 dark:text-rink-400"
                        : "text-ice-300 dark:text-ice-600"
                    }
                    strokeWidth={highlight === abbrev ? 2.5 : 1}
                    strokeOpacity={highlight && highlight !== abbrev ? 0.35 : 1}
                    onMouseEnter={() => setHighlight(abbrev)}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          )}
        </div>
      </Card>

      <div className="overflow-x-auto rounded border border-ice-200 dark:border-ice-700">
        <table className="w-full min-w-[34rem] text-sm">
          <thead className="bg-ice-100 dark:bg-ice-700">
            <tr className="text-left text-xs tracking-wide text-ice-400 uppercase">
              <Th onClick={() => toggle("rank")} active={sort === "rank"} desc={descending}>
                #
              </Th>
              <Th onClick={() => toggle("abbrev")} active={sort === "abbrev"} desc={descending}>
                Team
              </Th>
              <Th align="right" onClick={() => toggle("rank")} active={false} desc={false}>
                Elo
              </Th>
              <Th
                align="right"
                onClick={() => toggle("elo_7d_change")}
                active={sort === "elo_7d_change"}
                desc={descending}
              >
                7d
              </Th>
              <Th
                align="right"
                onClick={() => toggle("win_prob_vs_average")}
                active={sort === "win_prob_vs_average"}
                desc={descending}
              >
                vs average
              </Th>
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-ice-800">
            {rows.map((team) => (
              <tr
                key={team.abbrev}
                onMouseEnter={() => setHighlight(team.abbrev)}
                onMouseLeave={() => setHighlight(null)}
                className="border-t border-ice-100 first:border-0 hover:bg-ice-50 dark:border-ice-700/60 dark:hover:bg-ice-700/40"
              >
                <td className="tabular px-3 py-2 text-ice-400">{team.rank}</td>
                <td className="px-3 py-2">
                  <Link
                    to={`/team/${team.abbrev}`}
                    className="hover:text-blade-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-rink-500 dark:hover:text-blade-400"
                  >
                    <TeamMark abbrev={team.abbrev} size={22} />
                  </Link>
                </td>
                <td className="tabular px-3 py-2 text-right font-medium">{team.elo.toFixed(1)}</td>
                <td
                  className={`tabular px-3 py-2 text-right ${
                    team.elo_7d_change > 0
                      ? "text-good-500 dark:text-good-400"
                      : team.elo_7d_change < 0
                        ? "text-rink-500 dark:text-rink-400"
                        : "text-ice-400"
                  }`}
                >
                  {team.elo_7d_change === 0 ? "—" : signed(team.elo_7d_change)}
                </td>
                <td className="tabular px-3 py-2 text-right">{pct(team.win_prob_vs_average)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-ice-400">
        <strong>vs average</strong> is the win probability against a league-average opponent on
        neutral ice. <strong>7d</strong> is movement over the last seven days the league played,
        so it reads as dashes outside the season.
      </p>

      <Provenance
        generatedAt={ratings.data.generated_at}
        modelVersion={ratings.data.model_version}
      />
    </>
  );

  function toggle(key: SortKey) {
    if (key === sort) {
      setDescending((d) => !d);
    } else {
      setSort(key);
      setDescending(false);
    }
  }
}

function compare(a: TeamRating, b: TeamRating, key: SortKey): number {
  if (key === "abbrev") return a.abbrev.localeCompare(b.abbrev);
  if (key === "rank") return a.rank - b.rank;
  return b[key] - a[key];
}

function Th({
  children,
  onClick,
  active,
  desc,
  align = "left",
}: {
  children: string;
  onClick: () => void;
  active: boolean;
  desc: boolean;
  align?: "left" | "right";
}) {
  return (
    <th scope="col" className={`px-3 py-2 font-medium ${align === "right" ? "text-right" : ""}`}>
      <button
        type="button"
        onClick={onClick}
        aria-sort={active ? (desc ? "descending" : "ascending") : "none"}
        className="uppercase hover:text-ice-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-rink-500 dark:hover:text-ice-200"
      >
        {children}
        {active ? (desc ? " ↓" : " ↑") : ""}
      </button>
    </th>
  );
}

interface TooltipPayload {
  dataKey?: string | number;
  value?: number;
}

function HistoryTooltip({
  active,
  payload,
  label,
  highlight,
}: {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: string;
  highlight: string | null;
}) {
  if (!active || !payload?.length) return null;
  const row = highlight
    ? payload.find((p) => p.dataKey === highlight)
    : [...payload].sort((a, b) => (b.value ?? 0) - (a.value ?? 0))[0];
  if (!row) return null;

  return (
    <div className="rounded border border-ice-200 bg-white px-2 py-1 text-xs shadow-sm dark:border-ice-600 dark:bg-ice-800">
      <span className="text-ice-400">{label ? shortDate(label) : ""}</span>{" "}
      <strong className="font-semibold">{String(row.dataKey)}</strong>{" "}
      <span className="tabular">{(row.value ?? 0).toFixed(1)}</span>
    </div>
  );
}
