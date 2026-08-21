"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { getPostLoginPath } from "@/lib/roles";
import { PageLoader } from "@/components/PageLoader";

export default function RegisterPage() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [fullName, setFullName] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [emailDeliveryOk, setEmailDeliveryOk] = useState(true);

  // Already signed in? Nothing to register — send them to their own home.
  useEffect(() => {
    if (!authLoading && user) router.replace(getPostLoginPath(user));
  }, [authLoading, user, router]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const res = await apiFetch<{ email_delivery_ok: boolean }>("/auth/register", {
        method: "POST",
        auth: false,
        body: JSON.stringify({ full_name: fullName, username, email, password }),
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
    return <div className="page-frame text-fg-muted"><PageLoader size="md" /></div>;
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

  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center px-6 py-16">
      <h1 className="text-2xl font-bold text-fg">Create your account</h1>
      <p className="mt-1 text-sm text-fg-muted">
        Account signup is open every day. The AI Weekly Exam has its own separate registration window, open every
        Thursday.
      </p>
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
          <label className="label" htmlFor="username">
            Username
          </label>
          <input
            id="username"
            required
            minLength={3}
            maxLength={30}
            pattern="[a-z0-9_]+"
            title="Lowercase letters, numbers, and underscores only."
            className="input mt-1.5"
            placeholder="e.g. jordan_23"
            value={username}
            onChange={(e) => setUsername(e.target.value.toLowerCase())}
          />
          <p className="mt-1 text-xs text-fg-subtle">
            Your unique @handle — how others find and invite you to connect and to elimination battles. 3-30
            characters: lowercase letters, numbers, and underscores only.
          </p>
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
        <button type="submit" disabled={submitting} className="btn-primary w-full">
          {submitting ? "Creating account…" : "Create account"}
        </button>
      </form>
      <p className="mt-6 text-center text-sm text-fg-muted">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-brand-600 underline dark:text-brand-400">
          Sign in
        </Link>
      </p>
      <p className="mt-2 text-center text-sm text-fg-muted">
        Want to teach here instead?{" "}
        <Link href="/register/instructor" className="font-medium text-brand-600 underline dark:text-brand-400">
          Apply to teach
        </Link>
      </p>
    </div>
  );
}
