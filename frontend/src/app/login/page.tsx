"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { getPostLoginPath } from "@/lib/roles";

/** Split auth shell: a brand panel (desktop) beside the form card. Used by the
 *  sign-in and 2FA steps so both feel like one considered screen. */
function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="mx-auto grid min-h-[calc(100dvh-var(--shell-h))] max-w-6xl items-center gap-8 px-4 py-12 lg:grid-cols-2 lg:gap-16">
      <aside className="hidden border-r border-ink-700 pr-16 lg:block">
        <p className="text-sm font-medium text-fg-subtle">Survival School</p>
        <h2 className="mt-3 max-w-xs">One account for your courses, exams, and certificates.</h2>
        <p className="mt-4 max-w-sm text-sm text-fg-muted">
          Sign in to pick up where you left off. Students, instructors, and admins use the same sign-in — you&rsquo;ll land
          on the right home for your role.
        </p>
        <dl className="mt-8 space-y-4 text-sm">
          <ShellFact k="Exams" v="Graded on the server, the moment you submit" />
          <ShellFact k="Certificates" v="Each carries a public verification link" />
          <ShellFact k="Schedule" v="Weekend exams, Saturday & Sunday (IST)" />
        </dl>
      </aside>
      <div className="w-full">{children}</div>
    </div>
  );
}

function ShellFact({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold uppercase tracking-wide text-fg-subtle">{k}</dt>
      <dd className="mt-0.5 text-fg-muted">{v}</dd>
    </div>
  );
}

export default function LoginPage() {
  const router = useRouter();
  const { login, verifyMfa } = useAuth();
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);
  const [mfaToken, setMfaToken] = useState<string | null>(null);
  const [mfaCode, setMfaCode] = useState("");

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await login(email, password);
      if (result.mfaRequired) {
        setMfaToken(result.mfaToken);
      } else {
        router.push(getPostLoginPath(result.user));
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const onVerifyMfa = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!mfaToken) return;
    setError(null);
    setSubmitting(true);
    try {
      const me = await verifyMfa(mfaToken, mfaCode.trim());
      router.push(getPostLoginPath(me));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Invalid code. Please try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const resendVerification = async () => {
    if (!email || resending) return;
    setResending(true);
    try {
      const res = await apiFetch<{ message: string }>("/auth/resend-verification", {
        method: "POST",
        auth: false,
        body: JSON.stringify({ email }),
      });
      toast.show(res.message, "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't resend the email.", "error");
    } finally {
      setResending(false);
    }
  };

  if (mfaToken) {
    return (
      <AuthShell>
        <div className="card mx-auto max-w-md p-7 sm:p-8">
          <h1 className="text-2xl font-bold text-fg">Two-factor verification</h1>
          <p className="mt-1.5 text-sm text-fg-muted">
            Enter the 6-digit code from your authenticator app, or one of your backup codes.
          </p>
          <form onSubmit={onVerifyMfa} className="mt-7 space-y-5">
            <div>
              <label className="label" htmlFor="mfa-code">Authentication code</label>
              <input
                id="mfa-code"
                autoFocus
                inputMode="numeric"
                className="input mt-1.5 font-mono text-lg tracking-[0.3em]"
                placeholder="123456"
                maxLength={10}
                value={mfaCode}
                onChange={(e) => setMfaCode(e.target.value)}
              />
            </div>
            {error && <p role="alert" className="text-sm font-medium text-danger">{error}</p>}
            <button type="submit" disabled={submitting || !mfaCode.trim()} className="btn-primary w-full">
              {submitting ? "Verifying…" : "Verify and sign in"}
            </button>
            <button
              type="button"
              onClick={() => { setMfaToken(null); setMfaCode(""); setError(null); }}
              className="btn-ghost w-full"
            >
              ← Back to sign in
            </button>
          </form>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell>
      <div className="card mx-auto max-w-md p-7 sm:p-8">
        <h1 className="text-2xl font-bold text-fg">Welcome back</h1>
        <p className="mt-1.5 text-sm text-fg-muted">Sign in to continue learning.</p>

        <form onSubmit={onSubmit} className="mt-7 space-y-5">
          <div>
            <label className="label" htmlFor="email">Email</label>
            <input id="email" type="email" autoComplete="email" required className="input mt-1.5" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <div className="flex items-center justify-between">
              <label className="label" htmlFor="password">Password</label>
              <Link href="/forgot-password" className="text-xs font-medium text-brand-600 hover:underline dark:text-brand-400">Forgot password?</Link>
            </div>
            <input id="password" type="password" autoComplete="current-password" required className="input mt-1.5" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && (
            <p role="alert" className="text-sm font-medium text-danger">
              {error}{" "}
              <button
                type="button"
                onClick={resendVerification}
                disabled={!email || resending}
                className="underline hover:no-underline disabled:opacity-50"
              >
                {resending ? "Sending…" : "Resend verification email"}
              </button>
            </p>
          )}
          <button type="submit" disabled={submitting} className="btn-primary w-full">
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="mt-6 text-center text-sm text-fg-muted">
          New here? <Link href="/register" className="font-medium text-brand-600 underline dark:text-brand-400">Create an account</Link>
        </p>
      </div>
    </AuthShell>
  );
}
