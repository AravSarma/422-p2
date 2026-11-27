import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiClient, ApiError, SKILL_TIERS, type SkillTier } from "../services/ApiClient";
import { UO_EMAIL_PATTERN } from "../config";
import { Alert, btn, inputCls, labelCls } from "./ui";

const TIER_HELP: Record<SkillTier, string> = {
  Beginner: "New to chess or still learning how the pieces move",
  Casual: "Know the rules and play for fun",
  Tournament: "Play rated games or study seriously",
};

/**
 * FR-04 / FR-05: account-free registration. Target: a newcomer completes
 * this on a phone in under 30 seconds (SDS §3.3).
 */
export default function RegistrationModal({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [tier, setTier] = useState<SkillTier>("Beginner");
  const [errors, setErrors] = useState<{ name?: string; email?: string; form?: string }>({});
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const firstInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    firstInput.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  function validate() {
    const next: typeof errors = {};
    if (!name.trim()) next.name = "Please enter your name.";
    if (!email.trim()) next.email = "Please enter your UO email.";
    else if (!UO_EMAIL_PATTERN.test(email.trim())) next.email = "Use your @uoregon.edu email address.";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!validate()) return;
    setSubmitting(true);
    try {
      await ApiClient.registerMember(name.trim(), email.trim().toLowerCase(), tier);
      setDone(true);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setErrors({ email: "This email is already registered with the club." });
      } else if (err instanceof ApiError && err.status === 400) {
        setErrors({ form: err.message });
      } else {
        setErrors({ form: err instanceof Error ? err.message : "Registration failed." });
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-slate-900/60 sm:items-center sm:p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="register-title"
        className="max-h-[92vh] w-full overflow-y-auto rounded-t-2xl bg-white p-5 shadow-xl sm:max-w-md sm:rounded-2xl"
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 id="register-title" className="text-xl font-bold text-slate-900">
              Join the club
            </h2>
            <p className="text-sm text-slate-600">No account or password needed.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="-mr-1 rounded-md p-1 text-2xl leading-none text-slate-600 hover:bg-slate-100 hover:text-slate-900"
          >
            ×
          </button>
        </div>

        {done ? (
          <div className="space-y-4">
            <Alert kind="success">
              <p className="font-semibold">You're registered, {name.trim().split(" ")[0]}! ♟</p>
              <p className="mt-1">
                Your starting club rating is <strong>1200</strong>. Come to the next meeting and an officer will
                pair you up for a game.
              </p>
            </Alert>
            <button type="button" className={`${btn.primary} w-full`} onClick={onClose}>
              Done
            </button>
          </div>
        ) : (
          <form onSubmit={handleSubmit} noValidate className="space-y-4">
            {errors.form && <Alert kind="error">{errors.form}</Alert>}

            <div>
              <label htmlFor="reg-name" className={labelCls}>
                Full name
              </label>
              <input
                id="reg-name"
                ref={firstInput}
                className={inputCls}
                autoComplete="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                aria-invalid={!!errors.name}
                aria-describedby={errors.name ? "reg-name-err" : undefined}
              />
              {errors.name && (
                <p id="reg-name-err" className="mt-1 text-sm text-red-700">
                  {errors.name}
                </p>
              )}
            </div>

            <div>
              <label htmlFor="reg-email" className={labelCls}>
                UO email
              </label>
              <input
                id="reg-email"
                type="email"
                inputMode="email"
                autoComplete="email"
                placeholder="duckname@uoregon.edu"
                className={inputCls}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-invalid={!!errors.email}
                aria-describedby={errors.email ? "reg-email-err" : undefined}
              />
              {errors.email && (
                <p id="reg-email-err" className="mt-1 text-sm text-red-700">
                  {errors.email}
                </p>
              )}
            </div>

            <fieldset>
              <legend className={labelCls}>Experience level</legend>
              <div className="space-y-2">
                {SKILL_TIERS.map((t) => (
                  <label
                    key={t}
                    className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 ${
                      tier === t ? "border-brand-700 bg-brand-50" : "border-slate-300 hover:bg-slate-50"
                    }`}
                  >
                    <input
                      type="radio"
                      name="tier"
                      value={t}
                      checked={tier === t}
                      onChange={() => setTier(t)}
                      className="mt-1 h-4 w-4 accent-brand-700"
                    />
                    <span>
                      <span className="block font-medium text-slate-900">{t}</span>
                      <span className="block text-sm text-slate-600">{TIER_HELP[t]}</span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            <button type="submit" className={`${btn.primary} w-full`} disabled={submitting}>
              {submitting ? "Registering…" : "Register"}
            </button>
            <p className="text-xs text-slate-600">
              Your name and email stay on the club's own computer and are deleted if you leave the club.
            </p>
          </form>
        )}
      </div>
    </div>
  );
}
