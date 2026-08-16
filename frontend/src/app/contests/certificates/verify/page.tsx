"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";
import { formatDate } from "@/lib/format";

interface ContestCertificateOut {
  valid: boolean;
  certificate_number?: string;
  contest_id: string;
  contest_title: string;
  rank: number;
  score_percent: number;
  issued_at: string;
  expires_at?: string | null;
  revoked: boolean;
  student_full_name?: string | null;
  verify_url?: string | null;
  invalid_reason?: string | null;
}

export default function VerifyContestCertificatePage() {
  const [number, setNumber] = useState("");
  const [result, setResult] = useState<ContestCertificateOut | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [checking, setChecking] = useState(false);

  const check = async (e: React.FormEvent) => {
    e.preventDefault();
    setChecking(true);
    setResult(null);
    setNotFound(false);
    try {
      const res = await apiFetch<ContestCertificateOut>(
        `/contests/certificates/verify/${encodeURIComponent(number)}`,
        { auth: false }
      );
      if (!res.valid && res.invalid_reason === "not_found") {
        setNotFound(true);
      } else {
        setResult(res);
      }
    } catch {
      setNotFound(true);
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="mx-auto max-w-lg px-6 py-16">
      <h1 className="text-2xl font-bold text-fg">Verify a contest certificate</h1>
      <p className="mt-1 text-sm text-fg-muted">Enter a Survival School contest certificate number to confirm it&apos;s genuine.</p>

      <form onSubmit={check} className="mt-8 flex gap-3">
        <input className="input" placeholder="SS-CONTEST-XXXXXXXXXXXX" value={number} onChange={(e) => setNumber(e.target.value.toUpperCase())} required />
        <button type="submit" disabled={checking} className="btn-primary shrink-0">{checking ? "Checking…" : "Verify"}</button>
      </form>

      {result && result.valid && (
        <div className="card mt-8 border-emerald-500/40">
          <p className="text-sm font-semibold text-emerald-700 dark:text-emerald-400">✓ Valid certificate</p>
          <dl className="mt-4 space-y-2 text-sm">
            {result.student_full_name && <div className="flex justify-between"><dt className="text-fg-subtle">Student</dt><dd className="text-fg">{result.student_full_name}</dd></div>}
            <div className="flex justify-between"><dt className="text-fg-subtle">Certificate ID</dt><dd className="font-mono text-fg">{result.certificate_number}</dd></div>
            <div className="flex justify-between"><dt className="text-fg-subtle">Contest</dt><dd className="text-fg">{result.contest_title}</dd></div>
            <div className="flex justify-between"><dt className="text-fg-subtle">Rank</dt><dd className="text-fg">#{result.rank}</dd></div>
            <div className="flex justify-between"><dt className="text-fg-subtle">Score</dt><dd className="text-fg">{result.score_percent}%</dd></div>
            <div className="flex justify-between"><dt className="text-fg-subtle">Issued</dt><dd className="text-fg">{formatDate(result.issued_at)}</dd></div>
            {result.expires_at && <div className="flex justify-between"><dt className="text-fg-subtle">Valid until</dt><dd className="text-fg">{formatDate(result.expires_at)}</dd></div>}
          </dl>
          {result.certificate_number && <div className="mt-5 flex flex-wrap gap-3"><a href={`${process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1"}/contests/certificates/${encodeURIComponent(result.certificate_number)}/pdf`} target="_blank" rel="noreferrer" className="btn-primary">Download PDF</a><button type="button" className="btn-secondary" onClick={() => navigator.clipboard?.writeText(window.location.href)}>Copy page link</button></div>}
        </div>
      )}

      {result && !result.valid && result.invalid_reason !== "not_found" && (
        <div className="card mt-8 border-red-500/40">
          <p className="text-sm font-semibold text-red-700 dark:text-red-400">✗ Certificate is not valid</p>
          <p className="mt-2 text-sm text-fg-muted">Reason: {result.invalid_reason === "revoked" ? "revoked" : "expired"}.</p>
          <p className="mt-2 text-xs text-fg-subtle">Certificate {result.certificate_number}</p>
        </div>
      )}

      {notFound && <div className="card mt-8 border-red-500/40"><p className="text-sm font-semibold text-red-700 dark:text-red-400">✗ No matching certificate found</p></div>}
    </div>
  );
}
