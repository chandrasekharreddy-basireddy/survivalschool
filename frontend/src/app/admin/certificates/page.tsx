"use client";

import { useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { ApiError, apiFetch } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface PublicCertificateOut {
  valid: boolean;
  certificate_number: string | null;
  course_title: string | null;
  student_full_name: string | null;
  grade: string | null;
  score_percent: number | null;
  issued_at: string | null;
  expires_at: string | null;
  invalid_reason: string | null;
}

interface RevokeCertificateOut {
  certificate_number: string;
  revoked_at: string;
}

export default function AdminCertificatesPage() {
  const { user, loading } = useAuth();
  const toast = useToast();
  const [number, setNumber] = useState("");
  const [cert, setCert] = useState<PublicCertificateOut | null>(null);
  const [looking, setLooking] = useState(false);
  const [revoking, setRevoking] = useState(false);

  const lookup = async () => {
    const trimmed = number.trim();
    if (!trimmed) return;
    setLooking(true);
    setCert(null);
    try {
      const result = await apiFetch<PublicCertificateOut>(
        `/certificates/verify/${encodeURIComponent(trimmed)}`,
        { auth: false }
      );
      setCert(result);
      if (!result.valid && result.invalid_reason === "not_found") {
        toast.show("No certificate found with that number.", "error");
      }
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't look up that certificate.", "error");
    } finally {
      setLooking(false);
    }
  };

  const revoke = async () => {
    const trimmed = number.trim();
    if (!trimmed || !cert || cert.invalid_reason === "not_found") return;
    if (!window.confirm(`Revoke certificate ${trimmed}? This can't be undone.`)) return;
    setRevoking(true);
    try {
      await apiFetch<RevokeCertificateOut>(
        `/certificates/${encodeURIComponent(trimmed)}/revoke`,
        { method: "POST" }
      );
      toast.show("Certificate revoked.", "success");
      await lookup();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't revoke that certificate.", "error");
    } finally {
      setRevoking(false);
    }
  };

  if (loading) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user || !user.roles.some((r) => ["ADMIN", "SUPER_ADMIN"].includes(r))) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">This area is for admins.</p>
        <Link href="/dashboard" className="btn-secondary mt-6 inline-flex">Back to dashboard</Link>
      </div>
    );
  }

  const notFound = cert !== null && cert.invalid_reason === "not_found";
  const alreadyRevoked = cert !== null && cert.invalid_reason === "revoked";

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Certificates</h1>
      <p className="mt-1 text-sm text-fg-muted">Look up a certificate by number and revoke it if needed.</p>

      <div className="mt-6 flex gap-3">
        <input
          className="input flex-1"
          placeholder="Certificate number"
          value={number}
          onChange={(e) => setNumber(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") lookup(); }}
        />
        <button onClick={lookup} disabled={looking || !number.trim()} className="btn-secondary">
          {looking ? "Looking up…" : "Look up"}
        </button>
      </div>

      {cert && (
        <div className="card mt-6">
          {notFound ? (
            <p className="text-sm text-fg-muted">No certificate found with number &ldquo;{number.trim()}&rdquo;.</p>
          ) : (
            <>
              <div className="flex items-center justify-between">
                <h2 className="font-semibold text-fg">{cert.certificate_number}</h2>
                {cert.valid ? (
                  <span className="text-sm text-emerald-400">Valid</span>
                ) : alreadyRevoked ? (
                  <span className="text-sm text-red-400">Revoked</span>
                ) : (
                  <span className="text-sm text-amber-400">Expired</span>
                )}
              </div>
              <dl className="mt-4 grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-fg-subtle">Course</dt>
                  <dd className="text-fg">{cert.course_title ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-fg-subtle">Student</dt>
                  <dd className="text-fg">{cert.student_full_name ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-fg-subtle">Issued</dt>
                  <dd className="text-fg">{cert.issued_at ? new Date(cert.issued_at).toLocaleDateString() : "—"}</dd>
                </div>
                <div>
                  <dt className="text-fg-subtle">Grade</dt>
                  <dd className="text-fg">{cert.grade ?? "—"}{cert.score_percent != null ? ` (${cert.score_percent}%)` : ""}</dd>
                </div>
              </dl>

              <button
                onClick={revoke}
                disabled={revoking || alreadyRevoked}
                className="btn-secondary mt-6 border-red-500/40 text-red-400 hover:bg-red-500/10 disabled:opacity-50"
              >
                {alreadyRevoked ? "Already revoked" : revoking ? "Revoking…" : "Revoke this certificate"}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
