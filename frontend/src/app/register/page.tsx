"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { getPostLoginPath } from "@/lib/roles";

interface RegistrationStatus {
  is_open: boolean;
  next_open_at: string | null;
  message: string;
}

function formatCountdown(nextOpenAt: string | null, now: number): string | null {
  if (!nextOpenAt || now <= 0) return null;
  const seconds = Math.max(0, Math.floor((new Date(nextOpenAt).getTime() - now) / 1000));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  return `${days}d ${String(hours).padStart(2, "0")}h ${String(minutes).padStart(2, "0")}m ${String(secs).padStart(2, "0")}s`;
}

export default function RegisterPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [emailDeliveryOk, setEmailDeliveryOk] = useState(true);
  const [status, setStatus] = useState<RegistrationStatus | null>(null);
  const [now, setNow] = useState(0);

  // Already signed in? Nothing to register — send them to their own home.
  useEffect(() => {
    if (!authLoading && user) router.replace(getPostLoginPath(user));
  }, [authLoading, user, router]);

  useEffect(() => {
    apiFetch<RegistrationStatus>("/auth/registration-status", { auth: false })
      .then(setStatus)
      // Fail closed, matching the backend's own fail-closed behavior
      // (registration_window_guard returns 503 if it can't check the window)
      // — showing "open" here on a network hiccup would let someone fill out
      // the whole form only to have the actual POST rejected.
      .catch(() =>
        setStatus({
          is_open: false,
          next_open_at: null,
          message: "Registration status is temporarily unavailable. Please try again shortly.",
        })
      );
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const countdown = formatCountdown(status?.next_open_at ?? null, now);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await apiFetch<{ email_delivery_ok: boolean }>("/auth/register", {
        method: "POST",
        auth: false,
        body: JSON.stringify({ full_name: fullName, email, password }),
      });
      setEmailDeliveryOk(res.email_delivery_ok);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (authLoading || user) {
    return <div className="page-frame text-fg-muted">Loading…</div>;
  }

  if (done) {
    return (
      <div className="mx-auto flex min-h-[70vh] max-w-md flex-col items-center justify-center px-6 text-center">
        <div className="card w-full p-6">
          {emailDeliveryOk ? (
            <>
              <h1 className="text-xl font-bold text-fg">Check your inbox</h1>
              <p className="mt-2 text-sm text-fg-muted">
                We sent a verification link to <span className="text-fg">{email}</span>. Click it to activate your
                account.
              </p>
            </>
          ) : (
            <>
              <h1 className="text-xl font-bold text-fg">Account created</h1>
              <p className="mt-2 text-sm text-danger">
                Your account was created, but we couldn&apos;t send the verification email to{" "}
                <span className="text-fg">{email}</span> right now.
              </p>
            </>
          )}
          <Link href="/login" className="btn-primary mt-6 w-full">
            Go to sign in
          </Link>
        </div>
      </div>
    );
  }

  if (status && !status.is_open) {
    return (
      <div className="mx-auto flex min-h-[70vh] max-w-lg flex-col justify-center px-6 py-16 text-center">
        <div className="section-card">
          <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-brand-600 dark:text-brand-400">
            Registration window
          </p>
          <h1 className="mt-2 text-2xl font-bold text-fg">Signups are closed right now</h1>
          <p className="mt-3 text-sm text-fg-muted">{status.message}</p>
          {countdown && (
            <p className="mt-6 font-mono text-lg font-bold text-teal" aria-live="polite">
              Next opening: {countdown}
            </p>
          )}
          <div className="mt-6 flex flex-col gap-2 sm:flex-row sm:justify-center">
            <Link href="/login" className="btn-secondary">
              Sign in
            </Link>
            <Link href="/courses" className="btn-primary">
              Browse courses
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-6 py-16">
      <h1 className="text-2xl font-bold text-fg">Create your account</h1>
      <p className="mt-1 text-sm text-fg-muted">Registration is open on Thursdays (IST).</p>
      <form onSubmit={onSubmit} className="mt-8 space-y-5">
        <div>
          <label className="label" htmlFor="full_name">
            Full name
          </label>
          <input
            id="full_name"
            required
            className="input mt-1.5"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="email">
            Email
          </label>
          <input
            id="email"
            type="email"
            autoComplete="email"
            required
            className="input mt-1.5"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={10}
            className="input mt-1.5"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <p className="mt-1 text-xs text-fg-subtle">
            At least 10 characters, with uppercase, lowercase, a digit, and a symbol.
          </p>
        </div>
        {error && (
          <p role="alert" className="text-sm font-medium text-danger">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting || status === null || status.is_open === false}
          className="btn-primary w-full"
        >
          {submitting ? "Creating account…" : "Create account"}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-fg-muted">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-brand-600 underline dark:text-brand-400">
          Sign in
        </Link>
      </p>
    </div>
  );
}
