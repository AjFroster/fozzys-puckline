import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useTrack } from "../lib/api";
import { longDate, pct, seasonLabel, shortDate } from "../lib/format";
import { Card, Loading, PageTitle, Problem, Provenance } from "../components/Chrome";

const asNumber = (v: unknown): number => (typeof v === "number" ? v : Number(v) || 0);

export default function TrackPage() {
  const track = useTrack();

  if (track.loading) return <Loading label="Loading the season record" />;
  if (track.error) return <Problem>{track.error}</Problem>;
  if (!track.data || !track.data.summary) {
    return <Problem>No games graded yet this season. Check back after opening night.</Problem>;
  }

  const { season, complete, through, points, summary, biggest_misses, rolling_window } = track.data;
  const beating = summary.log_loss < summary.baseline_log_loss;

  return (
    <>
      <PageTitle
        sub={`${seasonLabel(season)} · ${complete ? "final" : "in progress"}${
          through ? ` · through ${longDate(through)}` : ""
        }`}
      >
        Season record
      </PageTitle>

      <Card className="mb-8 p-5">
        <dl className="tabular grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Stat label="Called correctly" value={`${summary.correct} of ${summary.games}`} big />
          <Stat label="Accuracy" value={pct(summary.accuracy)} big />
          <Stat
            label="Log loss"
            value={`${summary.log_loss.toFixed(4)}`}
            note={`baseline ${summary.baseline_log_loss.toFixed(4)}`}
            big
          />
          <Stat label="Over/under" value={pct(summary.over_under_hit_rate)} big />
        </dl>
        <p
          className={`mt-4 border-t border-ice-100 pt-3 text-sm dark:border-ice-700 ${
            beating ? "text-good-500 dark:text-good-400" : "text-rink-500 dark:text-rink-400"
          }`}
        >
          {beating
            ? "Beating the always-home baseline on the season."
            : "Losing to the always-home baseline on the season."}
        </p>
      </Card>

      <h2 className="mb-3 font-display text-xl font-semibold tracking-wide uppercase">
        Accuracy through the season
      </h2>
      <Card className="mb-8 p-4">
        <p className="mb-3 text-sm text-ice-500 dark:text-ice-300">
          The solid line is the running season total. The faint line is the last{" "}
          {rolling_window} games — cumulative numbers stop moving once a few hundred games
          are in, so a cold streak only shows up in the trailing window.
        </p>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points} margin={{ top: 4, right: 8, bottom: 4, left: -12 }}>
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
                domain={[0.25, 0.8]}
                ticks={[0.3, 0.4, 0.5, 0.6, 0.7, 0.8]}
                tickFormatter={(v: number) => pct(v, 0)}
                tick={{ fontSize: 11 }}
                width={44}
                stroke="currentColor"
                className="text-ice-400"
              />
              <ReferenceLine
                y={0.5}
                stroke="currentColor"
                className="text-ice-300 dark:text-ice-600"
                strokeDasharray="4 4"
              />
              <Tooltip
                labelFormatter={(l) => (typeof l === "string" ? shortDate(l) : "")}
                formatter={(value, name) => [pct(asNumber(value)), String(name)]}
                contentStyle={{ fontSize: 12, borderRadius: 4 }}
              />
              <Line
                type="monotone"
                dataKey="rolling_accuracy"
                name={`last ${rolling_window}`}
                dot={false}
                connectNulls
                isAnimationActive={false}
                stroke="currentColor"
                className="text-ice-300 dark:text-ice-600"
                strokeWidth={1.5}
              />
              <Line
                type="monotone"
                dataKey="accuracy"
                name="season"
                dot={false}
                isAnimationActive={false}
                stroke="currentColor"
                className="text-rink-500 dark:text-rink-400"
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 text-xs text-ice-400">
          The dashed line is a coin flip. Early swings are small samples, not form.
        </p>
      </Card>

      <h2 className="mb-3 font-display text-xl font-semibold tracking-wide uppercase">
        Against the baseline
      </h2>
      <Card className="mb-8 p-4">
        <p className="mb-3 text-sm text-ice-500 dark:text-ice-300">
          Log loss is the honest measure in a sport this close to a coin flip. Below the
          dashed baseline means the model is adding something over simply picking the home
          team every night.
        </p>
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points} margin={{ top: 4, right: 8, bottom: 4, left: -4 }}>
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
                domain={[0.6, 0.76]}
                ticks={[0.6, 0.64, 0.68, 0.72, 0.76]}
                tickFormatter={(v: number) => v.toFixed(2)}
                tick={{ fontSize: 11 }}
                width={44}
                stroke="currentColor"
                className="text-ice-400"
              />
              <Tooltip
                labelFormatter={(l) => (typeof l === "string" ? shortDate(l) : "")}
                formatter={(value, name) => [asNumber(value).toFixed(5), String(name)]}
                contentStyle={{ fontSize: 12, borderRadius: 4 }}
              />
              <Line
                type="monotone"
                dataKey="baseline_log_loss"
                name="baseline"
                dot={false}
                isAnimationActive={false}
                stroke="currentColor"
                className="text-ice-400"
                strokeDasharray="5 4"
                strokeWidth={1.5}
              />
              <Line
                type="monotone"
                dataKey="log_loss"
                name="model"
                dot={false}
                isAnimationActive={false}
                stroke="currentColor"
                className="text-rink-500 dark:text-rink-400"
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {biggest_misses.length > 0 ? (
        <>
          <h2 className="mb-3 font-display text-xl font-semibold tracking-wide uppercase">
            Worst calls
          </h2>
          <Card className="mb-8 p-4">
            <p className="mb-4 text-sm text-ice-500 dark:text-ice-300">
              The games the model was most confident about and still got wrong. A track
              record that only shows the aggregate is easy to read as better than it is.
            </p>
            <div className="overflow-x-auto">
              <table className="tabular w-full min-w-[26rem] text-sm">
                <thead>
                  <tr className="border-b border-ice-200 text-left text-xs tracking-wide text-ice-400 uppercase dark:border-ice-700">
                    <th scope="col" className="pb-2 font-medium">Date</th>
                    <th scope="col" className="pb-2 font-medium">Result</th>
                    <th scope="col" className="pb-2 text-right font-medium">Model gave winner</th>
                  </tr>
                </thead>
                <tbody>
                  {biggest_misses.map((m) => (
                    <tr
                      key={m.game_id}
                      className="border-b border-ice-100 last:border-0 dark:border-ice-700/60"
                    >
                      <td className="py-2 whitespace-nowrap text-ice-400">{shortDate(m.date)}</td>
                      <td className="py-2">
                        <strong className="font-semibold">{m.winner}</strong> beat {m.loser}{" "}
                        <span className="text-ice-400">{m.score}</span>
                      </td>
                      <td className="py-2 text-right font-medium text-rink-500 dark:text-rink-400">
                        {pct(m.probability_given_to_winner)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </>
      ) : null}

      <Provenance
        generatedAt={track.data.generated_at}
        modelVersion={track.data.model_version}
      />
    </>
  );
}

function Stat({
  label,
  value,
  note,
  big = false,
}: {
  label: string;
  value: string;
  note?: string;
  big?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs tracking-wide text-ice-400 uppercase">{label}</dt>
      <dd
        className={`mt-0.5 font-medium text-ice-900 dark:text-ice-50 ${big ? "text-xl" : ""}`}
      >
        {value}
      </dd>
      {note ? <p className="text-xs text-ice-400">{note}</p> : null}
    </div>
  );
}
