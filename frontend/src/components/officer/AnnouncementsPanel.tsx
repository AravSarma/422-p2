import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiClient, type Announcement, type AnnouncementInput } from "../../services/ApiClient";
import { Alert, Card, EmptyState, Loading, btn, formatShortDate, inputCls, labelCls, parseDate } from "../ui";
import type { OfficerSession } from "./session";

const BLANK: AnnouncementInput = { title: "", body: "" };

/** FR-07: create / edit / delete announcements (shown newest-first publicly). */
export default function AnnouncementsPanel({ session }: { session: OfficerSession }) {
  const [items, setItems] = useState<Announcement[] | null>(null);
  const [editing, setEditing] = useState<Announcement | null>(null);
  const [form, setForm] = useState<AnnouncementInput>(BLANK);
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
        setItems(
          [...d.announcements].sort((a, b) => parseDate(b.created_at).getTime() - parseDate(a.created_at).getTime()),
        ),
      )
      .catch((e) => {
        setItems((p) => p ?? []);
        setStatus({ kind: "error", msg: e instanceof Error ? e.message : "Could not load announcements." });
      });
  }, []);

  useEffect(load, [load]);

  function reset() {
    setEditing(null);
    setForm(BLANK);
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.title.trim() || !form.body.trim()) {
      setStatus({ kind: "error", msg: "Title and message are both required." });
      return;
    }
    const payload = { title: form.title.trim(), body: form.body.trim() };
    setBusy(true);
    setStatus(null);
    try {
      if (editing) await ApiClient.updateAnnouncement(editing.id, payload, session.token);
      else await ApiClient.createAnnouncement(payload, session.token);
      setStatus({ kind: "success", msg: editing ? "Announcement updated." : "Announcement posted." });
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
      await ApiClient.deleteAnnouncement(id, session.token);
      setItems((p) => (p ?? []).filter((x) => x.id !== id));
      if (editing?.id === id) reset();
      setStatus({ kind: "success", msg: "Announcement deleted." });
    } catch (err) {
      report(err);
    } finally {
      setConfirmId(null);
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title={editing ? "Edit announcement" : "New announcement"}>
        <form onSubmit={submit} className="space-y-4" noValidate>
          {status && <Alert kind={status.kind}>{status.msg}</Alert>}
          <div>
            <label htmlFor="an-title" className={labelCls}>
              Title
            </label>
            <input
              id="an-title"
              className={inputCls}
              placeholder="Room Update: Next Thursday in EMU 119"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="an-body" className={labelCls}>
              Message
            </label>
            <textarea
              id="an-body"
              rows={5}
              className={inputCls}
              value={form.body}
              onChange={(e) => setForm({ ...form, body: e.target.value })}
            />
          </div>
          <div className="flex gap-2">
            <button type="submit" className={btn.primary} disabled={busy}>
              {busy ? "Saving…" : editing ? "Save changes" : "Post announcement"}
            </button>
            {editing && (
              <button type="button" className={btn.secondary} onClick={reset}>
                Cancel
              </button>
            )}
          </div>
        </form>
      </Card>

      <Card title="Posted announcements">
        {items === null ? (
          <Loading />
        ) : items.length === 0 ? (
          <EmptyState>Nothing posted yet.</EmptyState>
        ) : (
          <ul className="divide-y divide-slate-200">
            {items.map((a) => (
              <li key={a.id} className="py-3">
                <p className="font-medium text-slate-900">{a.title}</p>
                <p className="text-xs text-slate-600">{formatShortDate(a.created_at)}</p>
                <p className="mt-1 line-clamp-3 whitespace-pre-line break-words text-sm text-slate-700">{a.body}</p>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    className={btn.small}
                    onClick={() => {
                      setEditing(a);
                      setForm({ title: a.title, body: a.body });
                      setStatus(null);
                      window.scrollTo({ top: 0, behavior: "smooth" });
                    }}
                  >
                    Edit
                  </button>
                  {confirmId === a.id ? (
                    <>
                      <button
                        type="button"
                        className="rounded-md bg-red-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-800"
                        onClick={() => remove(a.id)}
                      >
                        Confirm delete
                      </button>
                      <button type="button" className={btn.small} onClick={() => setConfirmId(null)}>
                        Keep
                      </button>
                    </>
                  ) : (
                    <button type="button" className={btn.small} onClick={() => setConfirmId(a.id)}>
                      Delete
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
