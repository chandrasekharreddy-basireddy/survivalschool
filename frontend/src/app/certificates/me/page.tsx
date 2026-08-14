"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";
import { formatDate } from "@/lib/format";

interface CertificateOut {
  certificate_number: string;
  course_title: string;
  issued_at: string;
  verify_url: string;
  grade: string | null;
  score_percent: number | null;
  skills: string[];
  specialization: string | null;
  instructor_name: string | null;
  expires_at: string | null;
  revoked: boolean;
}

export default function MyCertificatesPage() {
  const { user, loading } = useAuth();
  const [certs, setCerts] = useState<CertificateOut[] | null>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<CertificateOut[]>("/certificates/me").then(setCerts).catch(() => setCerts([]));
  }, [user]);

  if (loading) return <div className="mx-auto max-w-4xl px-6 py-16 text-slate-400">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-slate-300">Sign in to see your certificates.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10">
      <h1 className="text-2xl font-bold text-white">Your certificates</h1>
      <p className="mt-1 text-sm text-slate-400">Every course you&apos;ve completed and earned a certificate for.</p>

      {certs === null ? (
        <p className="mt-8 text-sm text-slate-500">Loading…</p>
      ) : certs.length === 0 ? (
        <div className="mt-8 rounded-lg border border-dashed border-ink-700 p-10 text-center text-sm text-slate-500">
          No certificates yet. Complete a course to earn your first one.{" "}
          <Link href="/courses" className="text-brand-400 hover:underline">Browse courses</Link>
        </div>
      ) : (
        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          {certs.map((c) => (
            <div key={c.certificate_number} className={`card ${c.revoked ? "opacity-50" : ""}`}>
              <div className="flex items-start justify-between gap-2">
                <h2 className="font-semibold text-white">{c.course_title}</h2>
                {c.grade && <span className="shrink-0 rounded-full border border-amber-400/40 px-2.5 py-0.5 text-xs font-bold text-amber-300">{c.grade}</span>}
              </div>
              <p className="mt-1 text-xs text-slate-500">Issued {formatDate(c.issued_at)}</p>
              {c.revoked && <p className="mt-2 text-xs font-semibold text-red-400">Revoked</p>}
              {c.skills.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {c.skills.slice(0, 4).map((s) => (
                    <span key={s} className="rounded bg-ink-800 px-2 py-0.5 text-[11px] text-slate-400">{s}</span>
                  ))}
                </div>
              )}
              <Link href={`/certificates/view/${c.certificate_number}`} className="btn-secondary mt-4 w-full !py-2 text-sm">
                View certificate
              </Link>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
