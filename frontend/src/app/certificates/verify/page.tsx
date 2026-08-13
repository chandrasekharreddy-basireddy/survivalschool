"use client";

import { useState } from "react";
import { apiFetch } from "@/lib/api";

interface VerifyResult {
  valid: boolean;
  certificate_number?: string;
  course_title?: string;
  student_first_name?: string;
  issued_at?: string;
}

export default function VerifyCertificatePage() {
  const [number, setNumber] = useState("");
  const [result, setResult] = useState<VerifyResult | null>(null);
  const [checking, setChecking] = useState(false);

  const check = async (e: React.FormEvent) => {
    e.preventDefault();
    setChecking(true);
    try {
      const res = await apiFetch<VerifyResult>(`/certificates/verify/${encodeURIComponent(number)}`, { auth: false });
      setResult(res);
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="mx-auto max-w-lg px-6 py-16">
      <h1 className="text-2xl font-bold text-white">Verify a certificate</h1>
      <p className="mt-1 text-sm text-slate-400">Enter a Survival School certificate number to confirm it&apos;s genuine.</p>

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

      {result && (
        <div className={`card mt-8 ${result.valid ? "border-emerald-500/40" : "border-red-500/40"}`}>
          {result.valid ? (
            <>
              <p className="text-sm font-semibold text-emerald-400">✓ Valid certificate</p>
              <dl className="mt-4 space-y-2 text-sm">
                <div className="flex justify-between"><dt className="text-slate-500">Certificate ID</dt><dd className="text-slate-200">{result.certificate_number}</dd></div>
                <div className="flex justify-between"><dt className="text-slate-500">Course</dt><dd className="text-slate-200">{result.course_title}</dd></div>
                <div className="flex justify-between"><dt className="text-slate-500">Awarded to</dt><dd className="text-slate-200">{result.student_first_name}</dd></div>
                <div className="flex justify-between"><dt className="text-slate-500">Issued</dt><dd className="text-slate-200">{result.issued_at?.slice(0, 10)}</dd></div>
              </dl>
            </>
          ) : (
            <p className="text-sm font-semibold text-red-400">✗ No matching certificate found</p>
          )}
        </div>
      )}
    </div>
  );
}
