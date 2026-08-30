import type { ReactNode } from "react";

export function PageTitle({ children, sub }: { children: ReactNode; sub?: ReactNode }) {
  return (
    <header className="mb-6">
      <h1 className="font-display text-3xl font-bold tracking-wide text-ice-900 uppercase sm:text-4xl dark:text-ice-50">
        {children}
      </h1>
      {sub ? <p className="mt-1 text-sm text-ice-400">{sub}</p> : null}
    </header>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`rounded border border-ice-200 bg-white dark:border-ice-700 dark:bg-ice-800 ${className}`}
    >
      {children}
    </div>
  );
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <p role="status" className="py-16 text-center text-sm text-ice-400">
      {label}…
    </p>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="py-16 text-center text-sm text-ice-400">{children}</p>;
}

export function Problem({ children }: { children: ReactNode }) {
  return (
    <div
      role="alert"
      className="rounded border border-rink-500/40 bg-rink-500/5 px-4 py-3 text-sm text-rink-500 dark:text-rink-400"
    >
      {children}
    </div>
  );
}

/**
 * Every page states when the data was made and which model made it. Stale data
 * has to be visible as stale rather than quietly presented as current.
 */
export function Provenance({
  generatedAt,
  modelVersion,
}: {
  generatedAt: string;
  modelVersion: string;
}) {
  return (
    <p className="mt-10 text-xs text-ice-400">
      Generated {new Date(generatedAt).toLocaleString()} · model{" "}
      <code className="tabular">{modelVersion}</code>
    </p>
  );
}
