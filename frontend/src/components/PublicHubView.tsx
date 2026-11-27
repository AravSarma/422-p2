import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiClient, ApiError, type Announcement, type ChessEvent } from "../services/ApiClient";
import { CLUB_TAGLINE, SOCIAL_LINKS, UO_EMAIL_PATTERN } from "../config";
import { Alert, Card, EmptyState, Loading, btn, formatEventDate, formatShortDate, inputCls, parseDate } from "./ui";

/**
 * Public landing page (FR-01, FR-02, FR-03). No login required.
 * Loads events + announcements in parallel on mount.
 */
export default function PublicHubView({ onRegister }: { onRegister: () => void }) {
  const [events, setEvents] = useState<ChessEvent[] | null>(null);
  const [announcements, setAnnouncements] = useState<Announcement[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await ApiClient.fetchPublicHubData();
      setEvents(data.events);
      setAnnouncements(data.announcements);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load club info.");
      setEvents((prev) => prev ?? []);
      setAnnouncements((prev) => prev ?? []);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // FR-01: only upcoming events, soonest first (backend may return all)
  const now = Date.now();
  const upcoming = (events ?? [])
    .filter((e) => parseDate(e.date_time).getTime() >= now - 3 * 60 * 60 * 1000)
    .sort((a, b) => parseDate(a.date_time).getTime() - parseDate(b.date_time).getTime());
  const next = upcoming[0];

  // FR-03: newest first
  const sortedAnnouncements = [...(announcements ?? [])].sort(
    (a, b) => parseDate(b.created_at).getTime() - parseDate(a.created_at).getTime(),
  );

  return (
    <div className="space-y-6">
      {error && (
        <Alert kind="error">
          {error}{" "}
          <button type="button" className="font-semibold underline" onClick={load}>
            Retry
          </button>
        </Alert>
      )}

      {/* Hero: the one thing a flyer-scanner needs — when & where */}
      <section className="overflow-hidden rounded-2xl bg-gradient-to-br from-brand-800 to-brand-900 p-5 text-white shadow sm:p-8">
        <p className="text-sm font-medium text-brand-100">{CLUB_TAGLINE}</p>
        {events === null ? (
          <p className="mt-4 text-brand-100">Loading next meeting…</p>
        ) : next ? (
          <div className="mt-4">
            <p className="text-xs font-semibold uppercase tracking-wider text-brand-100">Next meeting</p>
            <h1 className="mt-1 text-2xl font-bold sm:text-3xl">{next.title}</h1>
            <dl className="mt-3 grid gap-1 text-base sm:flex sm:gap-6">
              <div className="flex gap-2">
                <dt className="sr-only">When</dt>
                <dd>🕕 {formatEventDate(next.date_time)}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="sr-only">Where</dt>
                <dd>📍 {next.location}</dd>
              </div>
            </dl>
            {next.description && <p className="mt-3 max-w-prose text-brand-50">{next.description}</p>}
          </div>
        ) : (
          <h1 className="mt-4 text-2xl font-bold">No meetings scheduled yet — check back soon!</h1>
        )}
        <div className="mt-5 flex flex-wrap gap-3">
          <button
            type="button"
            onClick={onRegister}
            className="rounded-lg bg-white px-4 py-2.5 text-sm font-semibold text-brand-800 hover:bg-brand-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
          >
            Register — it's free
          </button>
          <a
            href="#/standings"
            className="rounded-lg border border-white/60 px-4 py-2.5 text-sm font-semibold text-white hover:bg-white/10"
          >
            View standings
          </a>
        </div>
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card title="Upcoming events">
            {events === null ? (
              <Loading />
            ) : upcoming.length === 0 ? (
              <EmptyState>No upcoming events posted.</EmptyState>
            ) : (
              <ul className="divide-y divide-slate-200">
                {upcoming.map((ev) => (
                  <EventRow key={ev.id} event={ev} />
                ))}
              </ul>
            )}
          </Card>

          <Card title="Announcements">
            {announcements === null ? (
              <Loading />
            ) : sortedAnnouncements.length === 0 ? (
              <EmptyState>No announcements right now.</EmptyState>
            ) : (
              <ul className="space-y-4">
                {sortedAnnouncements.map((a) => (
                  <li key={a.id} className="border-l-4 border-brand-600 pl-3">
                    <h3 className="font-semibold text-slate-900">{a.title}</h3>
                    <p className="text-xs text-slate-600">{formatShortDate(a.created_at)}</p>
                    <p className="mt-1 whitespace-pre-line break-words text-slate-800">{a.body}</p>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <Card title="Find us online" className="h-fit">
          <ul className="space-y-2">
            {SOCIAL_LINKS.map((s) => (
              <li key={s.label}>
                <a
                  href={s.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block rounded-lg border border-slate-200 p-3 hover:border-brand-700 hover:bg-brand-50"
                >
                  <span className="font-semibold text-brand-800">{s.label} ↗</span>
                  <span className="block text-sm text-slate-600">{s.description}</span>
                </a>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}

/** One event with an optional inline RSVP (FR-14). */
function EventRow({ event }: { event: ChessEvent }) {
  const [open, setOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState<{ kind: "error" | "success"; msg: string } | null>(null);
  const [count, setCount] = useState(event.rsvp_count);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!UO_EMAIL_PATTERN.test(email.trim())) {
      setStatus({ kind: "error", msg: "Enter the @uoregon.edu email you registered with." });
      return;
    }
    setBusy(true);
    try {
      const res = await ApiClient.rsvpToEvent(event.id, email.trim().toLowerCase());
      setCount(res?.rsvp_count ?? (count ?? 0) + 1);
      setStatus({ kind: "success", msg: "You're on the list — see you there!" });
      setOpen(false);
    } catch (err) {
      const msg =
        err instanceof ApiError && err.status === 404
          ? "We couldn't find that email. Register first, then RSVP."
          : err instanceof ApiError && err.status === 409
            ? "You've already RSVP'd to this event."
            : err instanceof Error
              ? err.message
              : "RSVP failed.";
      setStatus({ kind: "error", msg });
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="font-semibold text-slate-900">{event.title}</h3>
          <p className="text-sm text-slate-700">
            {formatEventDate(event.date_time)} · {event.location}
          </p>
          {event.description && <p className="mt-1 break-words text-sm text-slate-600">{event.description}</p>}
        </div>
        <div className="flex items-center gap-2">
          {typeof count === "number" && <span className="text-xs text-slate-600">{count} going</span>}
          {!open && (
            <button type="button" className={btn.small} onClick={() => setOpen(true)}>
              RSVP
            </button>
          )}
        </div>
      </div>
      {open && (
        <form onSubmit={submit} className="mt-2 flex flex-col gap-2 sm:flex-row" noValidate>
          <label htmlFor={`rsvp-${event.id}`} className="sr-only">
            Your UO email
          </label>
          <input
            id={`rsvp-${event.id}`}
            type="email"
            inputMode="email"
            placeholder="you@uoregon.edu"
            className={inputCls}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            autoFocus
          />
          <div className="flex gap-2">
            <button type="submit" className={btn.primary} disabled={busy}>
              {busy ? "…" : "Confirm"}
            </button>
            <button type="button" className={btn.secondary} onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
        </form>
      )}
      {status && (
        <div className="mt-2">
          <Alert kind={status.kind}>{status.msg}</Alert>
        </div>
      )}
    </li>
  );
}
