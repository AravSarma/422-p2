import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { ApiClient, type ChessEvent, type EventInput } from "../../services/ApiClient";
import { Alert, Card, EmptyState, Loading, btn, formatEventDate, inputCls, labelCls, parseDate } from "../ui";
import type { OfficerSession } from "./session";

const BLANK: EventInput = { title: "", date_time: "", location: "", description: "" };

/** FR-07: create / edit / delete events. */
export default function EventsPanel({ session }: { session: OfficerSession }) {
  const [events, setEvents] = useState<ChessEvent[] | null>(null);
  const [editing, setEditing] = useState<ChessEvent | null>(null);
  const [form, setForm] = useState<EventInput>(BLANK);
  const [status, setStatus] = useState<{ kind: "error" | "success"; msg: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);

  const report = (err: unknown) => {
    const msg = session.handleError(err);
    if (msg) setStatus({ kind: "error", msg });
  };

  const load = useCallback(() => {
    ApiClient.fetchPublicHubData()
      .then((d) =>
        setEvents([...d.events].sort((a, b) => parseDate(b.date_time).getTime() - parseDate(a.date_time).getTime())),
      )
      .catch((e) => {
        setEvents((p) => p ?? []);
        setStatus({ kind: "error", msg: e instanceof Error ? e.message : "Could not load events." });
      });
  }, []);

  useEffect(load, [load]);

  function startEdit(ev: ChessEvent) {
    setEditing(ev);
    setForm({
      title: ev.title,
      date_time: toLocalInput(ev.date_time),
      location: ev.location,
      description: ev.description,
    });
    setStatus(null);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function reset() {
    setEditing(null);
    setForm(BLANK);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.title.trim() || !form.date_time || !form.location.trim()) {
      setStatus({ kind: "error", msg: "Title, date/time, and location are required." });
      return;
    }
    const payload: EventInput = {
      title: form.title.trim(),
      date_time: form.date_time.length === 16 ? `${form.date_time}:00` : form.date_time,
      location: form.location.trim(),
      description: form.description.trim(),
    };
    setBusy(true);
    setStatus(null);
    try {
      if (editing) await ApiClient.updateEvent(editing.id, payload, session.token);
      else await ApiClient.createEvent(payload, session.token);
      setStatus({ kind: "success", msg: editing ? "Event updated." : "Event published." });
      reset();
      load();
    } catch (err) {
      report(err);
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    setStatus(null);
    try {
      await ApiClient.deleteEvent(id, session.token);
      setEvents((p) => (p ?? []).filter((x) => x.id !== id));
      if (editing?.id === id) reset();
      setStatus({ kind: "success", msg: "Event deleted." });
    } catch (err) {
      report(err);
    } finally {
      setConfirmId(null);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title={editing ? "Edit event" : "New event"}>
        <form onSubmit={submit} className="space-y-4" noValidate>
          {status && <Alert kind={status.kind}>{status.msg}</Alert>}
          <Field id="ev-title" label="Title">
            <input
              id="ev-title"
              className={inputCls}
              placeholder="Beginners Night: Pawn Endgames"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </Field>
          <Field id="ev-when" label="Date & time">
            <input
              id="ev-when"
              type="datetime-local"
              className={inputCls}
              value={form.date_time}
              onChange={(e) => setForm({ ...form, date_time: e.target.value })}
            />
          </Field>
          <Field id="ev-where" label="Location">
            <input
              id="ev-where"
              className={inputCls}
              placeholder="Straub 145"
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
            />
          </Field>
          <Field id="ev-desc" label="Description / workshop topic">
            <textarea
              id="ev-desc"
              rows={3}
              className={inputCls}
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
          </Field>
          <div className="flex gap-2">
            <button type="submit" className={btn.primary} disabled={busy}>
              {busy ? "Saving…" : editing ? "Save changes" : "Publish event"}
            </button>
            {editing && (
              <button type="button" className={btn.secondary} onClick={reset}>
                Cancel
              </button>
            )}
          </div>
        </form>
      </Card>

      <Card title="All events">
        {events === null ? (
          <Loading />
        ) : events.length === 0 ? (
          <EmptyState>No events yet.</EmptyState>
        ) : (
          <ul className="divide-y divide-slate-200">
            {events.map((ev) => {
              const past = parseDate(ev.date_time).getTime() < Date.now();
              return (
                <li key={ev.id} className="py-3">
                  <p className="font-medium text-slate-900">
                    {ev.title}
                    {past && <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">past</span>}
                  </p>
                  <p className="text-sm text-slate-600">
                    {formatEventDate(ev.date_time)} · {ev.location}
                    {typeof ev.rsvp_count === "number" && ` · ${ev.rsvp_count} RSVPs`}
                  </p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button type="button" className={btn.small} onClick={() => startEdit(ev)}>
                      Edit
                    </button>
                    {confirmId === ev.id ? (
                      <>
                        <button
                          type="button"
                          className="rounded-md bg-red-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-800"
                          onClick={() => remove(ev.id)}
                        >
                          Confirm delete
                        </button>
                        <button type="button" className={btn.small} onClick={() => setConfirmId(null)}>
                          Keep
                        </button>
                      </>
                    ) : (
                      <button type="button" className={btn.small} onClick={() => setConfirmId(ev.id)}>
                        Delete
                      </button>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}

function Field({ id, label, children }: { id: string; label: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className={labelCls}>
        {label}
      </label>
      {children}
    </div>
  );
}

/** Convert a backend timestamp to the "YYYY-MM-DDTHH:mm" a datetime-local input expects. */
function toLocalInput(value: string): string {
  const d = parseDate(value);
  if (isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
