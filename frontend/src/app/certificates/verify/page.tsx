"use client";

import { useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";

interface VerifyResult {
  valid: boolean;
  certificate_number?: string;
  course_title?: string;
  student_full_name?: string;
  grade?: string;
  issued_at?: string;
  invalid_reason?: string;
}

export default function VerifyCertificatePage() {
  const [number, setNumber] = useState("");
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const check = async (e: React.FormEvent) => {
    e.preventDefault();
    setChecking(true);
    setError(null);
    try {
      const res = await apiFetch<VerifyResult>(`/certificates/verify/${encodeURIComponent(number)}`, { auth: false });
      setResult(res);
    } catch {
      // Previously there was no catch at all — a network failure or malformed
      // response left an unhandled rejection and no feedback on screen.
      setResult(null);
      setError("We couldn't reach the verification service. Check your connection and try again.");
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="mx-auto max-w-lg px-6 py-16">
      <h1 className="text-2xl font-bold text-fg">Verify a certificate</h1>
      <p className="mt-1 text-sm text-fg-muted">Enter a Survival School certificate number to confirm it&apos;s genuine.</p>

      <form onSubmit={check} className="mt-8 flex gap-3">
        <input
          className="input"
          placeholder="SS-XXXXXXXXXXXX"
          value={number}
          onChange={(e) => setNumber(e.target.value.toUpperCase())}
          required
        />
        <button type="submit" disabled={checking} className="btn-primary shrink-0">
          {checking ? "Checking…" : "Verify"}
        </button>
      </form>

      {error && (
        <p role="alert" className="mt-6 text-sm font-medium text-danger">
          {error}
        </p>
      )}

      {result && (
        <div className={`card mt-8 ${result.valid ? "border-emerald-500/40" : "border-red-500/40"}`}>
          {result.valid ? (
            <>
              <p className="text-sm font-semibold text-emerald-700 dark:text-emerald-400">✓ Valid certificate</p>
              <dl className="mt-4 space-y-2 text-sm">
                <div className="flex justify-between"><dt className="text-fg-subtle">Certificate ID</dt><dd className="text-fg">{result.certificate_number}</dd></div>
                <div className="flex justify-between"><dt className="text-fg-subtle">Course</dt><dd className="text-fg">{result.course_title}</dd></div>
                <div className="flex justify-between"><dt className="text-fg-subtle">Awarded to</dt><dd className="text-fg">{result.student_full_name}</dd></div>
                {result.grade && <div className="flex justify-between"><dt className="text-fg-subtle">Grade</dt><dd className="text-fg">{result.grade}</dd></div>}
                <div className="flex justify-between"><dt className="text-fg-subtle">Issued</dt><dd className="text-fg">{result.issued_at?.slice(0, 10)}</dd></div>
              </dl>
              <Link href={`/certificates/view/${result.certificate_number}`} className="btn-primary mt-6 w-full">
                View full certificate
              </Link>
            </>
          ) : (
            <p className="text-sm font-semibold text-red-700 dark:text-red-400">
              ✗ {result.invalid_reason === "revoked" ? "This certificate has been revoked" : result.invalid_reason === "expired" ? "This certificate has expired" : "No matching certificate found"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
