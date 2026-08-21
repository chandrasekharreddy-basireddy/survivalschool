"use client";

import { Suspense, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { apiFetch, ApiError } from "@/lib/api";
import { PageLoader } from "@/components/PageLoader";

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={<div className="mx-auto max-w-md px-6 py-24 text-center text-fg-muted"><PageLoader size="md" /></div>}>
      <ResetPasswordInner />
    </Suspense>
  );
}

function ResetPasswordInner() {
  const params = useSearchParams();
  const router = useRouter();
  const token = params.get("token") || "";
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    try {
      await apiFetch("/auth/reset-password", {
        method: "POST", auth: false,
        body: JSON.stringify({ token, new_password: password }),
      });
      setDone(true);
      setTimeout(() => router.push("/login"), 1500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Reset failed.");
    }
  };

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-6 py-16">
      <h1 className="text-2xl font-bold text-fg">Set a new password</h1>
      {done ? (
        <p className="mt-8 text-sm text-emerald-700 dark:text-emerald-400">Password updated. Redirecting to sign in…</p>
      ) : (
        <form onSubmit={onSubmit} className="mt-8 space-y-5">
          <div>
            <label className="label" htmlFor="password">New password</label>
            <input id="password" type="password" required minLength={10} className="input" value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && <p role="alert" className="text-sm text-red-700 dark:text-red-400">{error}</p>}
          <button type="submit" className="btn-primary w-full">Update password</button>
        </form>
      )}
    </div>
  );
}
