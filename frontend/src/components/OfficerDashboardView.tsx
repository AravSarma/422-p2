import { useCallback, useMemo, useState, type FormEvent } from "react";
import { ApiClient, ApiError } from "../services/ApiClient";
import { Alert, Card, btn, inputCls, labelCls } from "./ui";
import EventsPanel from "./officer/EventsPanel";
import AnnouncementsPanel from "./officer/AnnouncementsPanel";
import MatchEntryPanel from "./officer/MatchEntryPanel";
import MembersPanel from "./officer/MembersPanel";
import FlyerPanel from "./officer/FlyerPanel";
import type { OfficerSession } from "./officer/session";

const TOKEN_KEY = "ecch.officerToken";

const TABS = [
  { id: "matches", label: "Match entry" },
  { id: "members", label: "Roster" },
  { id: "events", label: "Events" },
  { id: "announcements", label: "Announcements" },
  { id: "flyer", label: "QR flyer" },
] as const;
type TabId = (typeof TABS)[number]["id"];

/**
 * Officer Dashboard Mode (FR-06, FR-07, FR-08, FR-11, FR-13, FR-15).
 * Token is kept in sessionStorage so closing the browser tab logs out.
 */
export default function OfficerDashboardView() {
  const [token, setToken] = useState<string | null>(() => sessionStorage.getItem(TOKEN_KEY));
  const [notice, setNotice] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>("matches");

  const logout = useCallback(
    (message?: string) => {
      if (token) ApiClient.officerLogout(token).catch(() => {});
      sessionStorage.removeItem(TOKEN_KEY);
      setToken(null);
      setNotice(message ?? null);
    },
    [token],
  );

  /** Shared error handler: 401 anywhere drops back to the login screen. */
  const handleError = useCallback(
    (err: unknown): string => {
      if (err instanceof ApiError && err.isUnauthorized) {
        sessionStorage.removeItem(TOKEN_KEY);
        setToken(null);
        setNotice("Your session expired. Please log in again.");
        return "";
      }
      return err instanceof Error ? err.message : "Something went wrong.";
    },
    [],
  );

  // Stable identity so child effects that depend on `session` don't refetch every render
  const session = useMemo<OfficerSession | null>(
    () => (token ? { token, handleError } : null),
    [token, handleError],
  );

  if (!session) {
    return (
      <LoginForm
        notice={notice}
        onLogin={(t) => {
          sessionStorage.setItem(TOKEN_KEY, t);
          setToken(t);
          setNotice(null);
        }}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div className="no-print flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Officer dashboard</h1>
          <p className="text-sm text-slate-600">Changes appear on the public site immediately.</p>
        </div>
        <button type="button" className={btn.secondary} onClick={() => logout()}>
          Log out
        </button>
      </div>

      <div className="no-print -mx-4 overflow-x-auto px-4">
        <div role="tablist" aria-label="Dashboard sections" className="flex min-w-max gap-1 border-b border-slate-200">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              type="button"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${
                tab === t.id
                  ? "border-brand-700 text-brand-800"
                  : "border-transparent text-slate-600 hover:text-slate-900"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      <div role="tabpanel">
        {tab === "matches" && <MatchEntryPanel session={session} />}
        {tab === "members" && <MembersPanel session={session} />}
        {tab === "events" && <EventsPanel session={session} />}
        {tab === "announcements" && <AnnouncementsPanel session={session} />}
        {tab === "flyer" && <FlyerPanel />}
      </div>
    </div>
  );
}

function LoginForm({ notice, onLogin }: { notice: string | null; onLogin: (token: string) => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!username || !password) {
      setError("Enter your username and password.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { token } = await ApiClient.officerLogin(username, password);
      onLogin(token);
    } catch (err) {
      setError(
        err instanceof ApiError && (err.status === 401 || err.status === 403)
          ? "Incorrect username or password."
          : err instanceof Error
            ? err.message
            : "Login failed.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-sm">
      <Card title="Officer login">
        <form onSubmit={submit} className="space-y-4" noValidate>
          {notice && <Alert kind="info">{notice}</Alert>}
          {error && <Alert kind="error">{error}</Alert>}
          <div>
            <label htmlFor="login-user" className={labelCls}>
              Username
            </label>
            <input
              id="login-user"
              className={inputCls}
              autoComplete="username"
              autoCapitalize="none"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="login-pass" className={labelCls}>
              Password
            </label>
            <input
              id="login-pass"
              type="password"
              className={inputCls}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <button type="submit" className={`${btn.primary} w-full`} disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </Card>
      <p className="mt-3 text-center text-sm text-slate-600">For club officers only. Members don't need an account.</p>
    </div>
  );
}
