"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { getPostLoginPath } from "@/lib/roles";

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
      <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-6 py-16">
        <h1 className="text-2xl font-bold text-fg">Two-factor verification</h1>
        <p className="mt-1 text-sm text-fg-muted">Enter the 6-digit code from your authenticator app, or one of your backup codes.</p>

        <form onSubmit={onVerifyMfa} className="mt-8 space-y-5">
          <div>
            <label className="label" htmlFor="mfa-code">Authentication code</label>
            <input
              id="mfa-code"
              autoFocus
              inputMode="numeric"
              className="input font-mono tracking-widest"
              placeholder="123456"
              maxLength={10}
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value)}
            />
          </div>
          {error && <p role="alert" className="text-sm text-red-700 dark:text-red-400">{error}</p>}
          <button type="submit" disabled={submitting || !mfaCode.trim()} className="btn-primary w-full">
            {submitting ? "Verifying…" : "Verify and sign in"}
          </button>
          <button
            type="button"
            onClick={() => { setMfaToken(null); setMfaCode(""); setError(null); }}
            className="w-full text-center text-sm text-fg-muted hover:text-fg"
          >
            &larr; Back to sign in
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-6 py-16">
      <h1 className="text-2xl font-bold text-fg">Welcome back</h1>
      <p className="mt-1 text-sm text-fg-muted">Sign in to continue learning.</p>

      <form onSubmit={onSubmit} className="mt-8 space-y-5">
        <div>
          <label className="label" htmlFor="email">Email</label>
          <input id="email" type="email" required className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div>
          <div className="flex items-center justify-between">
            <label className="label" htmlFor="password">Password</label>
            <Link href="/forgot-password" className="text-xs text-brand-600 dark:text-brand-400 hover:underline">Forgot password?</Link>
          </div>
          <input id="password" type="password" required className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && (
          <p role="alert" className="text-sm text-red-700 dark:text-red-400">
            {error}{" "}
            <button
              type="button"
              onClick={resendVerification}
              disabled={!email || resending}
              className="text-brand-600 dark:text-brand-400 underline hover:no-underline disabled:opacity-50"
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
        New here? <Link href="/register" className="text-brand-600 underline dark:text-brand-400">Create an account</Link>
      </p>
    </div>
  );
}
