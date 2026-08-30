import { pct } from "../lib/format";

/**
 * Win probability, shown as a split bar with both numbers written out.
 *
 * The numbers are not optional decoration: probability is never encoded in
 * colour alone, so the bar stays readable without colour vision and for anyone
 * reading a screenshot.
 */
export function WinProbBar({
  awayAbbrev,
  homeAbbrev,
  homeProb,
  compact = false,
}: {
  awayAbbrev: string;
  homeAbbrev: string;
  homeProb: number;
  compact?: boolean;
}) {
  const awayProb = 1 - homeProb;
  const homeFavoured = homeProb >= 0.5;

  return (
    <div>
      <div
        className={`flex overflow-hidden rounded-full bg-ice-100 dark:bg-ice-700 ${
          compact ? "h-1.5" : "h-2"
        }`}
        role="img"
        aria-label={`${awayAbbrev} ${pct(awayProb)}, ${homeAbbrev} ${pct(homeProb)}`}
      >
        <div
          className={homeFavoured ? "bg-ice-300 dark:bg-ice-600" : "bg-blade-500 dark:bg-blade-400"}
          style={{ width: `${awayProb * 100}%` }}
        />
        <div
          className={homeFavoured ? "bg-blade-500 dark:bg-blade-400" : "bg-ice-300 dark:bg-ice-600"}
          style={{ width: `${homeProb * 100}%` }}
        />
      </div>
      <div className="tabular mt-1 flex justify-between text-xs text-ice-400">
        <span className={homeFavoured ? "" : "font-semibold text-ice-500 dark:text-ice-200"}>
          {pct(awayProb)}
        </span>
        <span className={homeFavoured ? "font-semibold text-ice-500 dark:text-ice-200" : ""}>
          {pct(homeProb)}
        </span>
      </div>
    </div>
  );
}
