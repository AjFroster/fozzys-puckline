interface PlaceholderProps {
  title: string;
  milestone: string;
  children: React.ReactNode;
}

/** Route shells landed in M0. Each is replaced by real UI in M5. */
export default function Placeholder({ title, milestone, children }: PlaceholderProps) {
  return (
    <section>
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-2 max-w-prose text-slate-600 dark:text-slate-400">{children}</p>
      <p className="mt-4 text-xs uppercase tracking-widest text-slate-400">Lands in {milestone}</p>
    </section>
  );
}
