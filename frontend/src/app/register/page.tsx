"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [emailDeliveryOk, setEmailDeliveryOk] = useState(true);

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
      // The account is real and created either way -- email_delivery_ok only
      // tells us whether the verification link actually got sent, so we
      // don't tell the user to "check your inbox" when we know it's not
      // there.
      setEmailDeliveryOk(res.email_delivery_ok);
      setDone(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  if (done) {
    return (
      <div className="mx-auto flex min-h-[70vh] max-w-md flex-col items-center justify-center px-6 text-center">
        <div className="card w-full">
          {emailDeliveryOk ? (
            <>
              <h1 className="text-xl font-bold text-fg">Check your inbox</h1>
              <p className="mt-2 text-sm text-fg-muted">
                We sent a verification link to <span className="text-fg">{email}</span>. Click it to activate your account.
              </p>
            </>
          ) : (
            <>
              <h1 className="text-xl font-bold text-fg">Account created</h1>
              <p className="mt-2 text-sm text-red-700 dark:text-red-400">
                Your account was created, but we couldn&apos;t send the verification email to{" "}
                <span className="text-fg">{email}</span> right now. Use &quot;Resend verification email&quot; on the
                verify-email page in a few minutes, or contact support if it keeps failing.
              </p>
            </>
          )}
          <Link href="/login" className="btn-primary mt-6 w-full">Go to sign in</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-6 py-16">
      <h1 className="text-2xl font-bold text-fg">Create your account</h1>
      <p className="mt-1 text-sm text-fg-muted">Start learning in minutes.</p>

      <form onSubmit={onSubmit} className="mt-8 space-y-5">
        <div>
          <label className="label" htmlFor="full_name">Full name</label>
          <input id="full_name" required className="input" value={fullName} onChange={(e) => setFullName(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="email">Email</label>
          <input id="email" type="email" required className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="password">Password</label>
          <input id="password" type="password" required minLength={10} className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
          <p className="mt-1 text-xs text-fg-subtle">At least 10 characters, with uppercase, lowercase, a digit, and a symbol.</p>
        </div>
        {error && <p role="alert" className="text-sm text-red-700 dark:text-red-400">{error}</p>}
        <button type="submit" disabled={submitting} className="btn-primary w-full">
          {submitting ? "Creating account…" : "Create account"}
        </button>
      </form>

      <p className="mt-6 text-center text-sm text-fg-muted">
        Already have an account? <Link href="/login" className="text-brand-600 underline dark:text-brand-400">Sign in</Link>
      </p>
    </div>
  );
}
