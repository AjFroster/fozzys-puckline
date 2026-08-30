/** Display helpers. No probability is computed here — that is Python's job. */

export const pct = (p: number, digits = 1): string => `${(p * 100).toFixed(digits)}%`;

/** American odds arrive already computed and fair; this only adds the sign. */
export const american = (odds: number): string => (odds > 0 ? `+${odds}` : `${odds}`);

export const signed = (value: number, digits = 1): string =>
  `${value > 0 ? "+" : value < 0 ? "−" : ""}${Math.abs(value).toFixed(digits)}`;

export const localTime = (iso: string | null): string => {
  if (!iso) return "TBD";
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });
};

export const longDate = (iso: string): string =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });

export const shortDate = (iso: string): string =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });

export const seasonLabel = (season: number): string => {
  const start = Math.floor(season / 10000);
  return `${start}-${String(start + 1).slice(2)}`;
};

export const logoUrl = (abbrev: string): string =>
  `https://assets.nhle.com/logos/nhl/svg/${abbrev}_light.svg`;

/** Shift a YYYY-MM-DD string by whole days without touching the timezone. */
export const addDays = (iso: string, days: number): string => {
  const date = new Date(`${iso}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
};
