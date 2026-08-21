"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { PageLoader } from "@/components/PageLoader";

interface ContestCertificateOut {
  certificate_number: string;
  contest_id: string;
  contest_title: string;
  rank: number;
  score_percent: number;
  issued_at: string;
}

export default function MyContestCertificatesPage() {
  const { user, loading } = useAuth();
  const [certs, setCerts] = useState<ContestCertificateOut[] | null>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<ContestCertificateOut[]>("/contests/me/certificates").then(setCerts).catch(() => setCerts([]));
  }, [user]);

  if (loading) return <div className="mx-auto max-w-4xl px-6 py-16 text-fg-muted"><PageLoader size="md" /></div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to see your contest certificates.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Your contest certificates</h1>
      <p className="mt-1 text-sm text-fg-muted">Awarded for top-3 finishes in a contest.</p>

      {certs === null ? (
        <p className="mt-8 text-sm text-fg-subtle"><PageLoader size="sm" /></p>
      ) : certs.length === 0 ? (
        <div className="mt-8 rounded-lg border border-dashed border-ink-700 p-10 text-center text-sm text-fg-subtle">
          No contest certificates yet. Finish in the top 3 of a contest to earn one.{" "}
          <Link href="/contests" className="text-brand-600 dark:text-brand-400 hover:underline">Browse contests</Link>
        </div>
      ) : (
        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          {certs.map((c) => (
            <div key={c.certificate_number} className="card">
              <div className="flex items-start justify-between gap-2">
                <h2 className="font-semibold text-fg">{c.contest_title}</h2>
                <span className="shrink-0 rounded-full border border-amber-400/40 px-2.5 py-0.5 text-xs font-bold text-amber-300">
                  #{c.rank}
                </span>
              </div>
              <p className="mt-1 text-xs text-fg-subtle">Issued {formatDate(c.issued_at)}</p>
              <p className="mt-3 text-sm text-fg-muted">Score: {c.score_percent}%</p>
              <p className="mt-2 font-mono text-xs text-fg-subtle">{c.certificate_number}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
