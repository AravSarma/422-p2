import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClient, type LeaderboardEntry, type MatchRecord } from "../services/ApiClient";
import { Alert, Card, EmptyState, Loading, displayOutcome, formatShortDate, inputCls } from "./ui";

/**
 * Live Elo leaderboard (FR-10) + recent results (UC-3).
 * Ranks come from the backend; this view never stores or computes them.
 * `refreshKey` lets a parent force a reload (e.g. after match entry).
 */
export default function StandingsView({ refreshKey = 0, compact = false }: { refreshKey?: number; compact?: boolean }) {
  const [rows, setRows] = useState<LeaderboardEntry[] | null>(null);
  const [matches, setMatches] = useState<MatchRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    setError(null);
    const [s, m] = await Promise.allSettled([ApiClient.fetchStandings(), ApiClient.fetchRecentMatches()]);
    if (s.status === "fulfilled") setRows(s.value);
    else {
      setRows((prev) => prev ?? []);
      setError(s.reason instanceof Error ? s.reason.message : "Could not load standings.");
    }
    // Match history is supplementary — fail quietly to an empty list
    setMatches(m.status === "fulfilled" ? m.value : []);
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (rows ?? []).filter((r) => !q || r.name.toLowerCase().includes(q));
  }, [rows, query]);

  const filteredMatches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (matches ?? [])
      .filter((m) => !q || m.white_label.toLowerCase().includes(q) || m.black_label.toLowerCase().includes(q))
      .slice(0, compact ? 5 : 20);
  }, [matches, query, compact]);

  return (
    <div className="space-y-6">
      {!compact && (
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Club standings</h1>
          <p className="text-slate-600">
            Elo ratings update automatically after every recorded club game. Everyone starts at 1200.
          </p>
        </div>
      )}

      {error && (
        <Alert kind="error">
          {error}{" "}
          <button type="button" className="font-semibold underline" onClick={load}>
            Retry
          </button>
        </Alert>
      )}

      <Card
        title="Leaderboard"
        action={
          <div className="w-full sm:w-56">
            <label htmlFor="standings-search" className="sr-only">
              Find a player
            </label>
            <input
              id="standings-search"
              type="search"
              placeholder="Find a player…"
              className={`${inputCls} py-1.5 text-sm`}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        }
      >
        {rows === null ? (
          <Loading />
        ) : filtered.length === 0 ? (
          <EmptyState>{rows.length === 0 ? "No rated members yet." : "No players match that name."}</EmptyState>
        ) : (
          <div className="-mx-4 overflow-x-auto sm:mx-0">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-600">
                  <th scope="col" className="w-12 px-4 py-2 sm:px-2">
                    #
                  </th>
                  <th scope="col" className="px-2 py-2">
                    Player
                  </th>
                  <th scope="col" className="px-2 py-2 text-right">
                    Rating
                  </th>
                  <th scope="col" className="hidden px-2 py-2 sm:table-cell">
                    Tier
                  </th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((r) => (
                  <tr key={`${r.rank}-${r.name}`} className="border-b border-slate-100 last:border-0">
                    <td className="px-4 py-2.5 font-semibold text-slate-700 sm:px-2">
                      {r.rank <= 3 ? ["🥇", "🥈", "🥉"][r.rank - 1] : r.rank}
                    </td>
                    <td className="max-w-[10rem] truncate px-2 py-2.5 font-medium text-slate-900 sm:max-w-none">
                      {r.name}
                      <span className="block text-xs font-normal text-slate-600 sm:hidden">{r.skill_tier}</span>
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono tabular-nums text-slate-900 sm:px-2">
                      {Math.round(r.rating)}
                    </td>
                    <td className="hidden px-2 py-2.5 text-slate-700 sm:table-cell">{r.skill_tier}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Recent games">
        {matches === null ? (
          <Loading />
        ) : filteredMatches.length === 0 ? (
          <EmptyState>No games recorded yet.</EmptyState>
        ) : (
          <ul className="divide-y divide-slate-100 text-sm">
            {filteredMatches.map((m) => (
              <li key={m.id} className="flex items-center justify-between gap-3 py-2">
                <span className="min-w-0 flex-1">
                  <span className="break-words">
                    <span aria-label="White">♔</span> {m.white_label}
                    <span className="mx-1 text-slate-500">vs</span>
                    <span aria-label="Black">♚</span> {m.black_label}
                  </span>
                  <span className="block text-xs text-slate-600">{formatShortDate(m.played_at)}</span>
                </span>
                <span className="shrink-0 rounded-md bg-slate-100 px-2 py-1 font-mono font-semibold text-slate-900">
                  {displayOutcome(m.outcome)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
