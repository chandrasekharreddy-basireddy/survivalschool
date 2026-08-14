"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-md px-6 py-24 text-center text-fg-muted">Loading…</div>}>
      <VerifyEmailInner />
    </Suspense>
  );
}

function VerifyEmailInner() {
  const params = useSearchParams();
  const token = params.get("token");
  const [status, setStatus] = useState<"pending" | "success" | "error">("pending");
  const [message, setMessage] = useState("");
  const [resendEmail, setResendEmail] = useState("");
  const [resending, setResending] = useState(false);
  const [resendMessage, setResendMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setStatus("error");
      setMessage("Missing verification token.");
      return;
    }
    apiFetch<{ message: string }>("/auth/verify-email", { method: "POST", auth: false, body: JSON.stringify({ token }) })
      .then((res) => {
        setStatus("success");
        setMessage(res.message);
      })
      .catch((err) => {
        setStatus("error");
        setMessage(err instanceof ApiError ? err.message : "Verification failed.");
      });
  }, [token]);

  const resendVerification = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resendEmail || resending) return;
    setResending(true);
    setResendMessage(null);
    try {
      const res = await apiFetch<{ message: string }>("/auth/resend-verification", {
        method: "POST",
        auth: false,
        body: JSON.stringify({ email: resendEmail }),
      });
      setResendMessage(res.message);
    } catch (err) {
      setResendMessage(err instanceof ApiError ? err.message : "Couldn't resend the email.");
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col items-center justify-center px-6 text-center">
      <div className="card w-full">
        {status === "pending" && <p className="text-fg-muted">Verifying your email…</p>}
        {status === "success" && (
          <>
            <h1 className="text-xl font-bold text-fg">Email verified 🎉</h1>
            <p className="mt-2 text-sm text-fg-muted">{message}</p>
            <Link href="/login" className="btn-primary mt-6 w-full">Sign in</Link>
          </>
        )}
        {status === "error" && (
          <>
            <h1 className="text-xl font-bold text-fg">Verification failed</h1>
            <p className="mt-2 text-sm text-red-400">{message}</p>
            <form onSubmit={resendVerification} className="mt-6 space-y-3 text-left">
              <div>
                <label className="label" htmlFor="resend-email">Resend verification email</label>
                <input
                  id="resend-email"
                  type="email"
                  required
                  className="input"
                  placeholder="you@example.com"
                  value={resendEmail}
                  onChange={(e) => setResendEmail(e.target.value)}
                />
              </div>
              {resendMessage && <p className="text-sm text-fg-muted">{resendMessage}</p>}
              <button type="submit" disabled={resending || !resendEmail} className="btn-secondary w-full">
                {resending ? "Sending…" : "Resend verification email"}
              </button>
            </form>
            <Link href="/login" className="btn-secondary mt-3 w-full">Back to sign in</Link>
          </>
        )}
      </div>
    </div>
  );
}
