import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ApiClient, type MatchOutcome, type Member } from "../../services/ApiClient";
import StandingsView from "../StandingsView";
import { Alert, Card, Loading, btn, labelCls, inputCls, outcomeLabel } from "../ui";
import type { OfficerSession } from "./session";

const OUTCOMES: MatchOutcome[] = ["1-0", "1/2-1/2", "0-1"];

/** FR-08 / FR-09: record a game; the backend recalculates both Elo ratings. */
export default function MatchEntryPanel({ session }: { session: OfficerSession }) {
  const [members, setMembers] = useState<Member[] | null>(null);
  const [whiteId, setWhiteId] = useState("");
  const [blackId, setBlackId] = useState("");
  const [outcome, setOutcome] = useState<MatchOutcome | "">("");
  const [status, setStatus] = useState<{ kind: "error" | "success"; msg: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    ApiClient.fetchMembers(session.token)
      .then(setMembers)
      .catch((e) => {
        setMembers([]);
        const msg = session.handleError(e);
        if (msg) setStatus({ kind: "error", msg });
      });
  }, [session, refreshKey]);

  const sorted = useMemo(
    () => [...(members ?? [])].sort((a, b) => a.name.localeCompare(b.name)),
    [members],
  );
  const nameOf = (id: string) => sorted.find((m) => String(m.id) === id)?.name ?? "?";

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!whiteId || !blackId || !outcome) {
      setStatus({ kind: "error", msg: "Pick both players and a result." });
      return;
    }
    if (whiteId === blackId) {
      setStatus({ kind: "error", msg: "White and Black must be different players." });
      return;
    }
    setBusy(true);
    setStatus(null);
    try {
      await ApiClient.submitMatch(Number(whiteId), Number(blackId), outcome, session.token);
      setStatus({
        kind: "success",
        msg: `Saved: ${nameOf(whiteId)} vs ${nameOf(blackId)} (${outcome}). Ratings updated.`,
      });
      setWhiteId("");
      setBlackId("");
      setOutcome("");
      setRefreshKey((k) => k + 1);
    } catch (err) {
      const msg = session.handleError(err);
      if (msg) setStatus({ kind: "error", msg });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Record a game">
        {members === null ? (
          <Loading label="Loading roster…" />
        ) : sorted.length < 2 ? (
          <Alert kind="info">At least two registered members are needed to record a game.</Alert>
        ) : (
          <form onSubmit={submit} className="space-y-4" noValidate>
            {status && <Alert kind={status.kind}>{status.msg}</Alert>}
            <PlayerSelect id="white" label="♔ White" value={whiteId} onChange={setWhiteId} members={sorted} exclude={blackId} />
            <PlayerSelect id="black" label="♚ Black" value={blackId} onChange={setBlackId} members={sorted} exclude={whiteId} />
            <fieldset>
              <legend className={labelCls}>Result</legend>
              <div className="grid grid-cols-3 gap-2">
                {OUTCOMES.map((o) => (
                  <label
                    key={o}
                    className={`cursor-pointer rounded-lg border p-2 text-center ${
                      outcome === o ? "border-brand-700 bg-brand-50 text-brand-900" : "border-slate-300 hover:bg-slate-50"
                    }`}
                  >
                    <input
                      type="radio"
                      name="outcome"
                      value={o}
                      className="sr-only"
                      checked={outcome === o}
                      onChange={() => setOutcome(o)}
                    />
                    <span className="block font-mono font-semibold">{o === "1/2-1/2" ? "½–½" : o}</span>
                    <span className="block text-xs text-slate-600">{outcomeLabel(o)}</span>
                  </label>
                ))}
              </div>
            </fieldset>
            <button type="submit" className={`${btn.primary} w-full`} disabled={busy}>
              {busy ? "Saving…" : "Submit result"}
            </button>
          </form>
        )}
      </Card>

      <StandingsView compact refreshKey={refreshKey} />
    </div>
  );
}

function PlayerSelect({
  id,
  label,
  value,
  onChange,
  members,
  exclude,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  members: Member[];
  exclude: string;
}) {
  return (
    <div>
      <label htmlFor={`player-${id}`} className={labelCls}>
        {label}
      </label>
      <select id={`player-${id}`} className={inputCls} value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Select a player…</option>
        {members.map((m) => (
          <option key={m.id} value={String(m.id)} disabled={String(m.id) === exclude}>
            {m.name} ({Math.round(m.current_rating)})
          </option>
        ))}
      </select>
    </div>
  );
}
