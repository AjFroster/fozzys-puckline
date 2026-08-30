import { logoUrl } from "../lib/format";

/** Club logo with the abbreviation beside it. Logos are hotlinked to the NHL CDN. */
export function TeamMark({
  abbrev,
  size = 28,
  className = "",
}: {
  abbrev: string;
  size?: number;
  className?: string;
}) {
  return (
    <span className={`flex items-center gap-2 ${className}`}>
      <img
        src={logoUrl(abbrev)}
        alt=""
        width={size}
        height={size}
        loading="lazy"
        className="shrink-0"
        style={{ width: size, height: size }}
      />
      <span className="font-display text-lg font-semibold tracking-wide">{abbrev}</span>
    </span>
  );
}
