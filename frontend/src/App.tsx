import { useEffect, useState } from "react";
import PublicHubView from "./components/PublicHubView";
import StandingsView from "./components/StandingsView";
import OfficerDashboardView from "./components/OfficerDashboardView";
import RegistrationModal from "./components/RegistrationModal";
import { btn } from "./components/ui";
import { CLUB_NAME } from "./config";

/**
 * Hash-based routing (#/, #/standings, #/officer) keeps the app a single
 * static index.html, so the Python http.server needs no SPA fallback logic.
 */
type Route = "home" | "standings" | "officer";

function routeFromHash(): Route {
  const h = window.location.hash.replace(/^#\/?/, "");
  if (h.startsWith("standings")) return "standings";
  if (h.startsWith("officer")) return "officer";
  return "home";
}

const NAV: { route: Route; label: string; href: string }[] = [
  { route: "home", label: "Home", href: "#/" },
  { route: "standings", label: "Standings", href: "#/standings" },
  { route: "officer", label: "Officers", href: "#/officer" },
];

export default function App() {
  const [route, setRoute] = useState<Route>(routeFromHash);
  const [registerOpen, setRegisterOpen] = useState(false);

  useEffect(() => {
    const onHash = () => {
      setRoute(routeFromHash());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  // QR flyers can link straight to the form with ?register or #/register
  useEffect(() => {
    if (window.location.hash.includes("register") || new URLSearchParams(window.location.search).has("register")) {
      setRegisterOpen(true);
    }
  }, []);

  return (
    <div className="flex min-h-screen flex-col">
      <header className="no-print sticky top-0 z-30 border-b border-brand-900 bg-brand-800 text-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-2 px-4 py-3">
          <a href="#/" className="flex min-w-0 items-center gap-2 font-bold">
            <span aria-hidden="true" className="text-2xl leading-none">
              ♞
            </span>
            <span className="truncate text-base sm:text-lg">
              <span className="hidden sm:inline">{CLUB_NAME}</span>
              <span className="sm:hidden">EC Chess Hub</span>
            </span>
          </a>
          <button
            type="button"
            onClick={() => setRegisterOpen(true)}
            className="shrink-0 rounded-lg bg-white px-3 py-2 text-sm font-semibold text-brand-800 hover:bg-brand-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          >
            Join the club
          </button>
        </div>
        <nav aria-label="Main" className="mx-auto max-w-5xl px-2">
          <ul className="flex">
            {NAV.map((n) => (
              <li key={n.route}>
                <a
                  href={n.href}
                  aria-current={route === n.route ? "page" : undefined}
                  className={`block border-b-2 px-3 py-2 text-sm font-medium ${
                    route === n.route
                      ? "border-white text-white"
                      : "border-transparent text-brand-100 hover:text-white"
                  }`}
                >
                  {n.label}
                </a>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-6">
        {route === "home" && <PublicHubView onRegister={() => setRegisterOpen(true)} />}
        {route === "standings" && <StandingsView />}
        {route === "officer" && <OfficerDashboardView />}
      </main>

      <footer className="no-print border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-2 px-4 py-4 text-sm text-slate-600">
          <span>{CLUB_NAME} · University of Oregon</span>
          <button type="button" className={btn.small} onClick={() => setRegisterOpen(true)}>
            Register
          </button>
        </div>
      </footer>

      {registerOpen && <RegistrationModal onClose={() => setRegisterOpen(false)} />}
    </div>
  );
}
