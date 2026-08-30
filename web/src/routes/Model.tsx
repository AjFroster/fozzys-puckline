import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { useMetrics } from "../lib/api";
import type { WindowMetrics } from "../types/contract";
import { longDate, pct, seasonLabel } from "../lib/format";
import { Card, Loading, PageTitle, Problem, Provenance } from "../components/Chrome";

/** Recharts passes tooltip values through as a loose union. */
const asNumber = (value: unknown): number => (typeof value === "number" ? value : Number(value) || 0);

export default function ModelPage() {
  const metrics = useMetrics();

  if (metrics.loading) return <Loading label="Loading the track record" />;
  if (metrics.error) return <Problem>{metrics.error}</Problem>;
  if (!metrics.data) return <Problem>No metrics published yet.</Problem>;

  const { windows, totals, by_season, holdout_season, recent } = metrics.data;
  const holdout = windows.find((w) => w.label.startsWith("holdout"));

  return (
    <>
      <PageTitle sub="How the model is built, and how it has actually done">
        Model
      </PageTitle>

      <p className="mb-8 max-w-prose text-sm text-ice-500 dark:text-ice-300">
        Two models run side by side. <strong>Elo</strong> answers who wins; it is unitless and
        cannot produce a goal total. A separate <strong>goal-rate model</strong> produces the
        over/under. Parameters are fitted walk-forward on the seasons{" "}
        <em>before</em> {seasonLabel(holdout_season)}, which is held out and never seen by any
        estimator — so the holdout numbers below measure the model on a season it was not
        shaped by.
      </p>

      {recent ? (
        <>
          <h2 className="mb-3 font-display text-xl font-semibold tracking-wide uppercase">
            Lately
          </h2>
          <Card className="mb-8 p-5">
            <p className="mb-4 text-sm text-ice-500 dark:text-ice-300">
              The last {recent.games} graded games, {longDate(recent.since)} to{" "}
              {longDate(recent.through)}. Wins and losses both — this is a rolling
              window, not a chosen one.
            </p>
            <dl className="tabular grid grid-cols-2 gap-4 sm:grid-cols-4">
              <Stat
                label="Called correctly"
                value={`${recent.correct} of ${recent.games}`}
              />
              <Stat label="Accuracy" value={pct(recent.accuracy)} />
              <Stat
                label="Log loss"
                value={`${recent.log_loss.toFixed(4)} vs ${recent.baseline_log_loss.toFixed(4)}`}
              />
              <Stat label="Over/under" value={pct(recent.over_under_hit_rate)} />
            </dl>
            <p
              className={`mt-4 border-t border-ice-100 pt-3 text-sm dark:border-ice-700 ${
                recent.log_loss < recent.baseline_log_loss
                  ? "text-good-500 dark:text-good-400"
                  : "text-rink-500 dark:text-rink-400"
              }`}
            >
              {recent.log_loss < recent.baseline_log_loss
                ? "Beating the always-home baseline over this window."
                : "Losing to the always-home baseline over this window."}
            </p>
          </Card>
        </>
      ) : null}

      <h2 className="mb-3 font-display text-xl font-semibold tracking-wide uppercase">
        Win probability
      </h2>
      <div className="mb-8 grid gap-3 sm:grid-cols-2">
        {windows.map((w) => (
          <WindowCard key={w.label} window={w} />
        ))}
      </div>

      <h2 className="mb-3 font-display text-xl font-semibold tracking-wide uppercase">
        Calibration
      </h2>
      <Card className="mb-8 p-4">
        <p className="mb-3 text-sm text-ice-500 dark:text-ice-300">
          Of the games called 60%, do about 60% actually win? Points on the diagonal are
          honest. Bins are judged in standard errors rather than percentage points, corrected
          for the number of bins tested — a 30-game bin carries far more noise than a
          1,800-game one.
        </p>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 8, right: 12, bottom: 8, left: -12 }}>
              <CartesianGrid
                stroke="currentColor"
                className="text-ice-200 dark:text-ice-700"
                strokeDasharray="2 4"
              />
              <XAxis
                type="number"
                dataKey="mean_predicted"
                domain={[0.2, 0.85]}
                tickFormatter={(v: number) => pct(v, 0)}
                tick={{ fontSize: 11 }}
                stroke="currentColor"
                className="text-ice-400"
                name="Predicted"
              />
              <YAxis
                type="number"
                dataKey="observed"
                domain={[0.2, 0.85]}
                tickFormatter={(v: number) => pct(v, 0)}
                tick={{ fontSize: 11 }}
                width={52}
                stroke="currentColor"
                className="text-ice-400"
                name="Observed"
              />
              <ZAxis type="number" dataKey="count" range={[40, 400]} name="Games" />
              <ReferenceLine
                segment={[
                  { x: 0.2, y: 0.2 },
                  { x: 0.85, y: 0.85 },
                ]}
                stroke="currentColor"
                className="text-ice-300 dark:text-ice-600"
                strokeDasharray="4 4"
              />
              <Tooltip
                cursor={{ strokeDasharray: "3 3" }}
                formatter={(value, name) =>
                  // Recharts hands these through untyped, so narrow here rather
                  // than claiming a signature the library does not guarantee.
                  [name === "Games" ? String(asNumber(value)) : pct(asNumber(value)), String(name)]
                }
                contentStyle={{ fontSize: 12, borderRadius: 4 }}
              />
              {windows.map((w, i) => (
                <Scatter
                  key={w.label}
                  name={w.label}
                  data={w.calibration.filter((b) => b.count >= 30)}
                  fill="currentColor"
                  className={
                    i === 0 ? "text-blade-500 dark:text-blade-400" : "text-rink-500 dark:text-rink-400"
                  }
                />
              ))}
            </ScatterChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-2 flex gap-4 text-xs text-ice-400">
          <span className="text-blade-500 dark:text-blade-400">● validation</span>
          <span className="text-rink-500 dark:text-rink-400">● holdout</span>
          <span>bubble size is games in the bin</span>
        </p>
      </Card>

      <h2 className="mb-3 font-display text-xl font-semibold tracking-wide uppercase">
        Every season
      </h2>
      <Card className="mb-8 p-4">
        <p className="mb-3 text-sm text-ice-500 dark:text-ice-300">
          Log loss against the always-home baseline. Lower is better, and below the dashed
          line means the model beat the baseline that season.
        </p>
        <div className="h-64 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={by_season.map((s) => ({ ...s, label: seasonLabel(s.season) }))}
              margin={{ top: 4, right: 8, bottom: 4, left: -8 }}
            >
              <CartesianGrid
                stroke="currentColor"
                className="text-ice-200 dark:text-ice-700"
                strokeDasharray="2 4"
                vertical={false}
              />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 11 }}
                stroke="currentColor"
                className="text-ice-400"
              />
              <YAxis
                domain={[0.63, 0.7]}
                tick={{ fontSize: 11 }}
                width={52}
                stroke="currentColor"
                className="text-ice-400"
              />
              <Tooltip
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
                strokeWidth={1.5}
                strokeDasharray="5 4"
              />
              <Line
                type="monotone"
                dataKey="log_loss"
                name="model"
                dot={{ r: 3 }}
                isAnimationActive={false}
                stroke="currentColor"
                className="text-rink-500 dark:text-rink-400"
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <h2 className="mb-3 font-display text-xl font-semibold tracking-wide uppercase">
        Total goals
      </h2>
      <div className="mb-8 grid gap-3 sm:grid-cols-2">
        {totals.map((t) => (
          <Card key={t.label} className="p-4">
            <h3 className="text-xs tracking-wide text-ice-400 uppercase">{t.label}</h3>
            <dl className="tabular mt-3 grid grid-cols-2 gap-3 text-sm">
              <Stat label="Over/under at fair line" value={pct(t.over_under_hit_rate)} />
              <Stat label="Model claimed" value={pct(t.model_claimed_rate)} />
              <Stat label="Total MAE" value={t.total_mae.toFixed(3)} />
              <Stat label="Games" value={String(t.games)} />
              <Stat label="Modelled OT rate" value={pct(t.modelled_tie_rate)} />
              <Stat label="Actual OT rate" value={pct(t.actual_tie_rate)} />
            </dl>
          </Card>
        ))}
      </div>

      {holdout ? (
        <Card className="p-4">
          <h3 className="font-display text-lg font-semibold tracking-wide uppercase">
            What to be sceptical of
          </h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ice-500 dark:text-ice-300">
            <li>
              The holdout season is the hardest in the window: a 20-day Olympic break, the
              highest rate of games past regulation, and the weakest home ice on record. Its
              skill of {pct(holdout.log_loss_skill, 2)} should be read next to the per-season
              chart, not on its own.
            </li>
            <li>
              NHL games are close to coin flips. Accuracy near{" "}
              {pct(holdout.baseline_accuracy, 0)} is what picking the home team every night
              gets you, so accuracy is a poor headline number and log loss is the honest one.
            </li>
            <li>
              The goal model carries one league-wide overtime rate and cannot anticipate a
              season being unusually prone to overtime.
            </li>
          </ul>
        </Card>
      ) : null}

      <Provenance
        generatedAt={metrics.data.generated_at}
        modelVersion={metrics.data.model_version}
      />
    </>
  );
}

function WindowCard({ window: w }: { window: WindowMetrics }) {
  return (
    <Card className="p-4">
      <div className="flex items-baseline justify-between">
        <h3 className="text-xs tracking-wide text-ice-400 uppercase">{w.label}</h3>
        <span
          className={`rounded-sm px-1.5 py-0.5 text-[10px] font-medium tracking-wide uppercase ${
            w.well_calibrated
              ? "bg-good-500/10 text-good-500 dark:text-good-400"
              : "bg-rink-500/10 text-rink-500 dark:text-rink-400"
          }`}
        >
          {w.well_calibrated ? "calibrated" : "miscalibrated"}
        </span>
      </div>
      <dl className="tabular mt-3 grid grid-cols-2 gap-3 text-sm">
        <Stat label="Log loss" value={w.log_loss.toFixed(5)} />
        <Stat label="Baseline" value={w.baseline_log_loss.toFixed(5)} />
        <Stat label="Skill" value={pct(w.log_loss_skill, 2)} />
        <Stat label="Accuracy" value={pct(w.accuracy)} />
        <Stat label="Games" value={String(w.games)} />
        <Stat
          label="Worst bin"
          value={`${w.worst_calibration_z.toFixed(2)}σ of ${w.calibration_threshold.toFixed(2)}`}
        />
      </dl>
    </Card>
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
