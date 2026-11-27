import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiClient, SKILL_TIERS, type Member } from "../../services/ApiClient";
import { Alert, Card, EmptyState, Loading, btn, formatShortDate, inputCls } from "../ui";
import type { OfficerSession } from "./session";

/** Roster view: tier counts (UC-1), un-enroll (FR-11/12), CSV export (FR-15). */
export default function MembersPanel({ session }: { session: OfficerSession }) {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [status, setStatus] = useState<{ kind: "error" | "success"; msg: string } | null>(null);
  const [query, setQuery] = useState("");
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(() => {
    ApiClient.fetchMembers(session.token)
      .then(setMembers)
      .catch((e) => {
        setMembers((prev) => prev ?? []);
        const msg = session.handleError(e);
        if (msg) setStatus({ kind: "error", msg });
      });
  }, [session]);

  useEffect(load, [load]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return [...(members ?? [])]
      .filter((m) => !q || m.name.toLowerCase().includes(q) || m.email.toLowerCase().includes(q))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [members, query]);

  async function unenroll(m: Member) {
    setBusyId(m.id);
    setStatus(null);
    try {
      await ApiClient.unenrollMember(m.id, session.token);
      setMembers((prev) => (prev ?? []).filter((x) => x.id !== m.id));
      setStatus({
        kind: "success",
        msg: `${m.name} was un-enrolled. Their personal info was deleted; past games now show “Former Member”.`,
      });
    } catch (err) {
      const msg = session.handleError(err);
      if (msg) setStatus({ kind: "error", msg });
    } finally {
      setBusyId(null);
      setConfirmId(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Stat label="Total members" value={members?.length} />
        {SKILL_TIERS.map((t) => (
          <Stat key={t} label={t} value={members?.filter((m) => m.skill_tier === t).length} />
        ))}
      </div>

      <Card
        title="Roster"
        action={
          <button
            type="button"
            className={btn.secondary}
            disabled={!members?.length}
            onClick={() => downloadCsv(members ?? [])}
          >
            ⬇ Export CSV
          </button>
        }
      >
        <div className="mb-3">
          <label htmlFor="roster-search" className="sr-only">
            Search members
          </label>
          <input
            id="roster-search"
            type="search"
            placeholder="Search by name or email…"
            className={inputCls}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        {status && (
          <div className="mb-3">
            <Alert kind={status.kind}>{status.msg}</Alert>
          </div>
        )}
        {members === null ? (
          <Loading />
        ) : filtered.length === 0 ? (
          <EmptyState>{members.length === 0 ? "No members registered yet." : "No matches."}</EmptyState>
        ) : (
          <ul className="divide-y divide-slate-200">
            {filtered.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <div className="min-w-0">
                  <p className="font-medium text-slate-900">{m.name}</p>
                  <p className="break-all text-sm text-slate-600">{m.email}</p>
                  <p className="text-xs text-slate-600">
                    {m.skill_tier} · Rating {Math.round(m.current_rating)} · Joined {formatShortDate(m.created_at)}
                  </p>
                </div>
                {confirmId === m.id ? (
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-slate-700">Delete permanently?</span>
                    <button
                      type="button"
                      className="rounded-md bg-red-700 px-3 py-2 text-sm font-semibold text-white hover:bg-red-800 disabled:opacity-60"
                      disabled={busyId === m.id}
                      onClick={() => unenroll(m)}
                    >
                      {busyId === m.id ? "…" : "Yes, un-enroll"}
                    </button>
                    <button type="button" className={btn.small} onClick={() => setConfirmId(null)}>
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button type="button" className={btn.danger} onClick={() => setConfirmId(m.id)}>
                    Un-enroll
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-600">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-900">{value ?? "–"}</p>
    </div>
  );
}

function csvCell(v: string | number): string {
  let s = String(v);
  // Neutralise spreadsheet formula injection from user-entered names
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function downloadCsv(members: Member[]) {
  const header = ["id", "name", "email", "skill_tier", "current_rating", "created_at"];
  const lines = [
    header.join(","),
    ...members.map((m) =>
      [m.id, m.name, m.email, m.skill_tier, Math.round(m.current_rating), m.created_at].map(csvCell).join(","),
    ),
  ];
  const blob = new Blob([lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `ec-chesshub-roster-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
