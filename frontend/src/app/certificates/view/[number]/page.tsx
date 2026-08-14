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
  course_title?: string;
  student_full_name?: string;
  grade?: string;
  score_percent?: number;
  skills?: string[];
  specialization?: string;
  instructor_name?: string;
  issued_at?: string;
  expires_at?: string;
  invalid_reason?: string;
}

export default function CertificateViewPage() {
  const params = useParams<{ number: string }>();
  const number = decodeURIComponent(params.number);
  const [cert, setCert] = useState<CertificateDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<CertificateDetail>(`/certificates/verify/${encodeURIComponent(number)}`, { auth: false })
      .then(setCert)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Couldn't load this certificate."));
  }, [number]);

  if (error) {
    return (
      <div className="mx-auto max-w-lg px-6 py-24 text-center">
        <p className="text-red-400">{error}</p>
      </div>
    );
  }

  if (!cert) {
    return <div className="mx-auto max-w-4xl px-6 py-24 text-center text-slate-400">Loading certificate…</div>;
  }

  if (!cert.valid) {
    return (
      <div className="mx-auto max-w-lg px-6 py-24 text-center">
        <h1 className="text-xl font-bold text-white">
          {cert.invalid_reason === "revoked" ? "This certificate has been revoked" : cert.invalid_reason === "expired" ? "This certificate has expired" : "Certificate not found"}
        </h1>
        <p className="mt-2 text-sm text-slate-500">
          Certificate number <span className="font-mono">{number}</span> could not be verified.
        </p>
        <Link href="/certificates/verify" className="btn-secondary mt-6 inline-flex">Try another number</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl px-6 py-10 print:max-w-full print:px-0 print:py-0">
      <div className="mb-6 flex items-center justify-between print:hidden">
        <Link href="/certificates/verify" className="text-sm text-slate-400 hover:text-white">&larr; Verify another certificate</Link>
        <div className="flex gap-3">
          <button onClick={() => window.print()} className="btn-secondary">Print / Save as PDF</button>
          <a
            href={`${API_BASE}/certificates/${encodeURIComponent(number)}/pdf`}
            target="_blank"
            rel="noreferrer"
            className="btn-primary"
          >
            Download PDF
          </a>
        </div>
      </div>

      <div className="relative overflow-hidden rounded-xl2 border-2 border-amber-400/60 bg-gradient-to-br from-ink-950 via-[#1e1b4b] to-ink-950 p-10 shadow-2xl print:rounded-none print:border-2 print:border-amber-500 sm:p-14">
        <p className="text-xs font-semibold uppercase tracking-[0.3em] text-amber-400">
          Survival School &mdash; Certificate of Completion
        </p>
        <h1 className="mt-3 text-3xl font-bold text-white sm:text-4xl">{cert.course_title}</h1>
        <p className="mt-1 text-sm text-slate-400">{cert.specialization || "Professional Certification Track"}</p>

        <p className="mt-10 text-2xl font-bold text-white sm:text-3xl">{cert.student_full_name}</p>
        <p className="mt-1 text-sm text-slate-400">has successfully completed this course</p>

        <div className="mt-6 flex flex-wrap items-center gap-4">
          {cert.grade && (
            <span className="inline-flex items-center rounded-full border border-amber-400/60 px-4 py-1.5 text-sm font-bold text-amber-300">
              Grade: {cert.grade}
            </span>
          )}
          {cert.score_percent != null && (
            <span className="text-sm text-slate-300">{cert.score_percent}% overall score</span>
          )}
        </div>

        {cert.skills && cert.skills.length > 0 && (
          <div className="mt-6">
            <p className="text-xs uppercase tracking-widest text-slate-500">Skills mastered</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {cert.skills.map((s) => (
                <span key={s} className="rounded-md border border-amber-400/30 bg-amber-400/10 px-2.5 py-1 text-xs text-amber-200">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="mt-12 flex flex-wrap items-end justify-between gap-6 border-t border-white/10 pt-6">
          <div className="text-xs leading-relaxed text-slate-500">
            <p>Certificate No. <span className="font-mono text-slate-300">{cert.certificate_number}</span></p>
            <p>Issued {formatDate(cert.issued_at)}{cert.expires_at ? ` · Valid until ${formatDate(cert.expires_at)}` : ""}</p>
            {cert.instructor_name && <p>Instructor: {cert.instructor_name}</p>}
          </div>
          <div className="flex items-center gap-4">
            <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full border-2 border-amber-400 text-center text-[9px] font-bold leading-tight text-amber-300">
              SS<br />VERIFIED
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`${API_BASE}/certificates/${encodeURIComponent(number)}/qr`}
              alt="Verification QR code"
              className="h-16 w-16 rounded bg-white p-1"
            />
          </div>
        </div>
      </div>

      <p className="mt-4 text-center text-xs text-slate-500 print:hidden">
        Anyone can independently verify this certificate at{" "}
        <Link href="/certificates/verify" className="text-brand-400 hover:underline">/certificates/verify</Link>.
      </p>

      <style jsx global>{`
        @media print {
          nav { display: none !important; }
          body { background: white !important; }
        }
      `}</style>
    </div>
  );
}
