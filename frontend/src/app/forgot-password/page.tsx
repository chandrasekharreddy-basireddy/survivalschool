"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await apiFetch("/auth/forgot-password", { method: "POST", auth: false, body: JSON.stringify({ email }) }).catch(() => {});
    setSent(true);
  };

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-6 py-16">
      <h1 className="text-2xl font-bold text-fg">Reset your password</h1>
      <p className="mt-1 text-sm text-fg-muted">We&apos;ll email you a reset link if that account exists.</p>

      {sent ? (
        <p className="mt-8 text-sm text-fg-muted">If that account exists, a reset email is on its way.</p>
      ) : (
        <form onSubmit={onSubmit} className="mt-8 space-y-5">
          <div>
            <label className="label" htmlFor="email">Email</label>
            <input id="email" type="email" required className="input" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <button type="submit" className="btn-primary w-full">Send reset link</button>
        </form>
      )}
    </div>
  );
}
