import { useMemo, useState } from "react";
import { useIndex, useSlate } from "../lib/api";
import { longDate } from "../lib/format";
import { Empty, Loading, PageTitle, Problem, Provenance } from "../components/Chrome";
import { GameCard } from "../components/GameCard";

export default function SlatePage() {
  const [date, setDate] = useState<string | null>(null);
  const index = useIndex();
  const slate = useSlate(date);

  const available = useMemo(
    () => new Set((index.data?.dates ?? []).map((d) => d.date)),
    [index.data],
  );

  const shown = slate.data?.date ?? null;
  // The stepper only offers days that were actually published, so it can never
  // walk the reader into a 404.
  const previous = shown ? nearest(available, shown, -1) : null;
  const next = shown ? nearest(available, shown, 1) : null;

  return (
    <>
      <PageTitle sub={shown ? longDate(shown) : undefined}>Today&rsquo;s slate</PageTitle>

      <div className="mb-6 flex items-center gap-2">
        <Step label="Previous day" to={previous} onPick={setDate}>
          ←
        </Step>
        <button
          type="button"
          onClick={() => setDate(null)}
          className="rounded border border-ice-200 px-3 py-1.5 text-sm text-ice-500 hover:border-blade-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-rink-500 dark:border-ice-700 dark:text-ice-200"
        >
          Latest
        </button>
        <Step label="Next day" to={next} onPick={setDate}>
          →
        </Step>
      </div>

      {slate.loading ? <Loading label="Loading the slate" /> : null}
      {slate.error ? <Problem>{slate.error}</Problem> : null}

      {slate.data && slate.data.games.length === 0 ? (
        <Empty>No games scheduled.</Empty>
      ) : null}

      {slate.data && slate.data.games.length > 0 ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {slate.data.games.map((game) => (
            <GameCard key={game.game_id} game={game} date={slate.data!.date} />
          ))}
        </div>
      ) : null}

      {slate.data ? (
        <Provenance
          generatedAt={slate.data.generated_at}
          modelVersion={slate.data.model_version}
        />
      ) : null}
    </>
  );
}

function nearest(available: Set<string>, from: string, direction: 1 | -1): string | null {
  const sorted = [...available].sort();
  const candidates = direction === 1 ? sorted : [...sorted].reverse();
  return candidates.find((d) => (direction === 1 ? d > from : d < from)) ?? null;
}

function Step({
  to,
  onPick,
  label,
  children,
}: {
  to: string | null;
  onPick: (date: string) => void;
  label: string;
  children: string;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={to === null}
      onClick={() => to && onPick(to)}
      className="rounded border border-ice-200 px-3 py-1.5 text-sm text-ice-500 hover:border-blade-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-rink-500 disabled:cursor-not-allowed disabled:opacity-40 dark:border-ice-700 dark:text-ice-200"
    >
      {children}
    </button>
  );
}
