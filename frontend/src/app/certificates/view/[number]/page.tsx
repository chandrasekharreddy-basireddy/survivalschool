"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { apiFetch, ApiError } from "@/lib/api";
import { formatDate } from "@/lib/format";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";

interface CertificateDetail {
  valid: boolean;
  certificate_number?: string;
  contest_title?: string;
  student_full_name?: string;
  rank?: number;
  score_percent?: number;
  issued_at?: string;
  expires_at?: string;
  invalid_reason?: string;
}

export default function CertificateViewPage() {
  const params = useParams<{ number: string }>();
  const number = decodeURIComponent(params.number);
  const [cert, setCert] = useState<CertificateDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [shared, setShared] = useState(false);

  useEffect(() => {
    apiFetch<CertificateDetail>(`/contests/certificates/verify/${encodeURIComponent(number)}`, { auth: false })
      .then(setCert)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Couldn't load this certificate."));
  }, [number]);

  const share = async () => {
    const url = window.location.href;
    const title = cert?.contest_title ? `Survival School certificate — ${cert.contest_title}` : "Survival School certificate";
    if (navigator.share) {
      await navigator.share({ title, text: `${cert?.student_full_name ?? "Student"} earned a verified Survival School certificate.`, url });
      return;
    }
    await navigator.clipboard.writeText(url);
    setShared(true);
    window.setTimeout(() => setShared(false), 1800);
  };

  if (error) {
    return <div className="mx-auto max-w-lg px-6 py-24 text-center"><p className="text-red-700 dark:text-red-400">{error}</p></div>;
  }
  if (!cert) {
    return <div className="mx-auto max-w-4xl px-6 py-24 text-center text-fg-muted">Loading certificate…</div>;
  }
  if (!cert.valid) {
    return (
      <div className="mx-auto max-w-lg px-6 py-24 text-center">
        <h1 className="text-xl font-bold text-fg">{cert.invalid_reason === "revoked" ? "This certificate has been revoked" : cert.invalid_reason === "expired" ? "This certificate has expired" : "Certificate not found"}</h1>
        <p className="mt-2 text-sm text-fg-subtle">Certificate number <span className="font-mono">{number}</span> could not be verified.</p>
        <Link href="/certificates/verify" className="btn-secondary mt-6 inline-flex">Try another number</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 print:max-w-full print:px-0 print:py-0">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Link href="/certificates/verify" className="text-sm text-fg-muted hover:text-fg">&larr; Verify another certificate</Link>
        <div className="flex flex-wrap gap-3">
          <button onClick={share} className="btn-secondary">{shared ? "Link copied" : "Share"}</button>
          <button onClick={() => window.print()} className="btn-secondary">Print / Save as PDF</button>
          <a href={`${API_BASE}/contests/certificates/${encodeURIComponent(number)}/pdf`} target="_blank" rel="noreferrer" className="btn-primary">Download PDF</a>
        </div>
      </div>

      {/* A certificate is a credential, so it reads as a real printed document:
          a light paper sheet with dark ink and a single restrained accent —
          not a themed UI card. Colours are fixed (not theme tokens) so it looks
          identical on screen, in dark mode, and on paper. */}
      <div className="overflow-hidden rounded-md border border-zinc-300 bg-white text-zinc-900 shadow-sm print:border-zinc-400 print:shadow-none">
        <div className="h-1.5 bg-brand-600" />
        <div className="p-8 sm:p-12">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-zinc-500">Certificate of Achievement</p>
              <p className="mt-1 text-sm font-semibold text-zinc-700">Survival School</p>
            </div>
            <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border-2 border-amber-500 text-center text-[8px] font-bold leading-tight text-amber-700">SS<br />VERIFIED</div>
          </div>

          <p className="mt-10 text-sm text-zinc-500">This certifies that</p>
          <p className="mt-1 text-3xl font-bold tracking-tight text-zinc-900 sm:text-4xl">{cert.student_full_name}</p>
          <p className="mt-4 text-sm text-zinc-500">finished rank #{cert.rank} in</p>
          <h1 className="mt-1 text-2xl font-semibold text-zinc-900 sm:text-3xl">{cert.contest_title}</h1>

          <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
            {cert.score_percent != null && <span className="font-semibold text-zinc-900">{cert.score_percent}% overall</span>}
          </div>

          <div className="mt-12 grid items-end gap-8 border-t border-zinc-200 pt-6 sm:grid-cols-[1fr_auto]">
            <div className="flex flex-wrap gap-x-12 gap-y-4">
              <div className="text-xs text-zinc-500"><div className="mb-1 font-semibold text-zinc-800">Survival School</div>Authorized Issuer</div>
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`${API_BASE}/contests/certificates/${encodeURIComponent(number)}/qr`} alt="Scan to verify this certificate" className="h-20 w-20 rounded border border-zinc-200 bg-white p-1 sm:justify-self-end" />
          </div>

          <div className="mt-6 border-t border-zinc-200 pt-4 text-xs leading-relaxed text-zinc-500">
            <p>Certificate No. <span className="font-mono text-zinc-700">{cert.certificate_number}</span></p>
            <p>Issued {formatDate(cert.issued_at)}{cert.expires_at ? ` · Valid until ${formatDate(cert.expires_at)}` : ""}</p>
          </div>
        </div>
      </div>

      <p className="mt-4 text-center text-xs text-fg-subtle print:hidden">Anyone can independently verify this certificate at <Link href="/certificates/verify" className="text-brand-600 underline dark:text-brand-400">/certificates/verify</Link>.</p>
      <style jsx global>{`@media print { nav { display:none !important; } body { background:white !important; } .print-hide { display:none !important; } }`}</style>
    </div>
  );
}
