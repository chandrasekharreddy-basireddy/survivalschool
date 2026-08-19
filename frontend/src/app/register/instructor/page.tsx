"use client";

import { useState } from "react";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

export default function InstructorApplicationPage() {
  const { user, loading: authLoading } = useAuth();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [institution, setInstitution] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [emailDeliveryOk, setEmailDeliveryOk] = useState(true);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (reason.trim().length < 20) {
      setError("Tell us a bit more — at least 20 characters about your teaching background.");
      return;
    }
    setSubmitting(true);
    try {
      const body: Record<string, string> = { reason, institution };
      if (!user) {
        body.full_name = fullName;
        body.email = email;
        body.password = password;
      }
      const res = await apiFetch<{ email_delivery_ok: boolean }>("/auth/instructor-applications", {
        method: "POST",
        auth: !!user,
        body: JSON.stringify(body),
      });
      setEmailDeliveryOk(res.email_delivery_ok);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (authLoading) {
    return <div className="page-frame text-fg-muted">Loading…</div>;
  }

  if (done) {
    return (
      <div className="mx-auto flex min-h-[70vh] max-w-md flex-col items-center justify-center px-6 text-center">
        <div className="card w-full p-6">
          <h1 className="text-xl font-bold text-fg">Application submitted</h1>
          <p className="mt-2 text-sm text-fg-muted">
            An admin will review your application. You&apos;ll be notified once a decision is made.
          </p>
          {!user && !emailDeliveryOk && (
            <p className="mt-2 text-sm text-danger">
              Your account was created, but we couldn&apos;t send a verification email right now — use
              &quot;resend verification&quot; from the sign-in page once you&apos;re ready.
            </p>
          )}
          <Link href={user ? "/dashboard" : "/login"} className="btn-primary mt-6 w-full">
            {user ? "Back to dashboard" : "Go to sign in"}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-6 py-16">
      <h1 className="text-2xl font-bold text-fg">Apply to teach</h1>
      <p className="mt-1 text-sm text-fg-muted">
        This isn&apos;t the student signup form — it&apos;s a review request. An admin grants instructor access
        after reading your application, it isn&apos;t automatic and isn&apos;t tied to the weekly exam
        registration window.
      </p>
      <form onSubmit={onSubmit} className="mt-8 space-y-5">
        {!user && (
          <>
            <div>
              <label className="label" htmlFor="full_name">Full name</label>
              <input id="full_name" required className="input mt-1.5" value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </div>
            <div>
              <label className="label" htmlFor="email">Email</label>
              <input id="email" type="email" autoComplete="email" required className="input mt-1.5" value={email} onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div>
              <label className="label" htmlFor="password">Password</label>
              <input id="password" type="password" autoComplete="new-password" required minLength={10} className="input mt-1.5" value={password} onChange={(e) => setPassword(e.target.value)} />
              <p className="mt-1 text-xs text-fg-subtle">At least 10 characters, with uppercase, lowercase, a digit, and a symbol.</p>
            </div>
          </>
        )}
        <div>
          <label className="label" htmlFor="institution">Institution (optional)</label>
          <input id="institution" className="input mt-1.5" value={institution} onChange={(e) => setInstitution(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="reason">Why do you want to teach here?</label>
          <textarea
            id="reason"
            required
            minLength={20}
            rows={5}
            className="input mt-1.5"
            placeholder="Your teaching background, subjects you'd cover, relevant experience…"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        {error && (
          <p role="alert" className="text-sm font-medium text-danger">{error}</p>
        )}
        <button type="submit" disabled={submitting} className="btn-primary w-full">
          {submitting ? "Submitting…" : "Submit application"}
        </button>
      </form>
      {!user && (
        <p className="mt-6 text-center text-sm text-fg-muted">
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-brand-600 underline dark:text-brand-400">Sign in</Link>{" "}
          first, then apply from your account.
        </p>
      )}
    </div>
  );
}
