"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const toast = useToast();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [resending, setResending] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
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
            <Link href="/forgot-password" className="text-xs text-brand-400 hover:underline">Forgot password?</Link>
          </div>
          <input id="password" type="password" required className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
        </div>
        {error && (
          <p role="alert" className="text-sm text-red-400">
            {error}{" "}
            <button
              type="button"
              onClick={resendVerification}
              disabled={!email || resending}
              className="text-brand-400 underline hover:no-underline disabled:opacity-50"
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
        New here? <Link href="/register" className="text-brand-400 hover:underline">Create an account</Link>
      </p>
    </div>
  );
}
