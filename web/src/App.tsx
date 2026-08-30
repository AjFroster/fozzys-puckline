import { Suspense, lazy } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import { Loading } from "./components/Chrome";
import GameDetail from "./routes/GameDetail";
import SlatePage from "./routes/Slate";

/*
 * The slate is the product and the common case is checking it on a phone, so it
 * and the matchup page load eagerly. Everything that draws a chart pulls in
 * Recharts, which is larger than the rest of the app put together, so those
 * routes are split out and fetched only when someone asks for them.
 */
const RatingsPage = lazy(() => import("./routes/Ratings"));
const TeamPage = lazy(() => import("./routes/Team"));
const ModelPage = lazy(() => import("./routes/Model"));
const TrackPage = lazy(() => import("./routes/Track"));

const nav = [
  { to: "/", label: "Slate", end: true },
  { to: "/ratings", label: "Ratings", end: false },
  { to: "/track", label: "Record", end: false },
  { to: "/model", label: "Model", end: false },
];

export default function App() {
  return (
    <div className="min-h-dvh bg-ice-50 text-ice-900 dark:bg-ice-900 dark:text-ice-50">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:m-2 focus:rounded focus:bg-white focus:px-3 focus:py-2 focus:text-sm dark:focus:bg-ice-800"
      >
        Skip to content
      </a>

      <header className="border-b border-ice-200 dark:border-ice-700">
        <div className="mx-auto flex max-w-5xl flex-wrap items-baseline gap-x-6 gap-y-2 px-4 py-4">
          <NavLink to="/" className="font-display text-xl font-bold tracking-wide uppercase">
            Fozzy&rsquo;s <span className="text-rink-500 dark:text-rink-400">Puckline</span>
          </NavLink>
          <nav className="flex gap-4 text-sm">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  isActive
                    ? "font-medium text-blade-500 dark:text-blade-400"
                    : "text-ice-400 hover:text-ice-500 dark:hover:text-ice-200"
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main id="main" className="mx-auto max-w-5xl px-4 py-8">
        <Suspense fallback={<Loading />}>
          <Routes>
            <Route path="/" element={<SlatePage />} />
            <Route path="/game/:date/:gameId" element={<GameDetail />} />
            <Route path="/ratings" element={<RatingsPage />} />
            <Route path="/team/:abbrev" element={<TeamPage />} />
            <Route path="/track" element={<TrackPage />} />
            <Route path="/model" element={<ModelPage />} />
            <Route
              path="*"
              element={<p className="py-16 text-center text-sm text-ice-400">Page not found.</p>}
            />
          </Routes>
        </Suspense>
      </main>

      <footer className="mx-auto max-w-5xl px-4 py-10 text-xs text-ice-400">
        <p>
          Informational and educational only. Not betting advice. All odds shown are fair — no
          vig — and are not sportsbook prices.
        </p>
        <p className="mt-1">
          Data from the NHL&rsquo;s public API. Not affiliated with the NHL.
        </p>
      </footer>
    </div>
  );
}
