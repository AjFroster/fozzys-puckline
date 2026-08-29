/** Display helpers. No probability is ever computed here — that is Python's job. */

export const pct = (p: number): string => `${(p * 100).toFixed(1)}%`;

/** Fair American odds from a probability. Positive numbers keep their sign. */
export const americanOdds = (p: number): string => {
  if (p <= 0 || p >= 1) return "—";
  const odds = p >= 0.5 ? -100 * (p / (1 - p)) : 100 * ((1 - p) / p);
  const rounded = Math.round(odds);
  return rounded > 0 ? `+${rounded}` : `${rounded}`;
};

export const localTime = (iso: string): string =>
  new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
