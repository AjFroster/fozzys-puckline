import { NavLink, Route, Routes } from "react-router-dom";
import Slate from "./routes/Slate";
import GameDetail from "./routes/GameDetail";
import Ratings from "./routes/Ratings";
import Team from "./routes/Team";
import Model from "./routes/Model";

const nav = [
  { to: "/", label: "Slate", end: true },
  { to: "/ratings", label: "Ratings", end: false },
  { to: "/model", label: "Model", end: false },
];

export default function App() {
  return (
    <div className="min-h-dvh bg-slate-50 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <header className="border-b border-slate-200 dark:border-slate-800">
        <div className="mx-auto flex max-w-5xl flex-wrap items-baseline gap-x-6 gap-y-2 px-4 py-4">
          <span className="text-lg font-semibold tracking-tight">Fozzy&rsquo;s Puckline</span>
          <nav className="flex gap-4 text-sm">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  isActive ? "font-medium text-sky-600 dark:text-sky-400" : "text-slate-500"
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-8">
        <Routes>
          <Route path="/" element={<Slate />} />
          <Route path="/game/:gameId" element={<GameDetail />} />
          <Route path="/ratings" element={<Ratings />} />
          <Route path="/team/:abbrev" element={<Team />} />
          <Route path="/model" element={<Model />} />
        </Routes>
      </main>

      <footer className="mx-auto max-w-5xl px-4 py-8 text-xs text-slate-500">
        Informational and educational only. Not betting advice.
      </footer>
    </div>
  );
}
