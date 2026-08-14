"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

interface AuditLogOut {
  id: string;
  actor_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  result: string;
  created_at: string;
}

export default function AuditLogsPage() {
  const { user, loading } = useAuth();
  const [logs, setLogs] = useState<AuditLogOut[] | null>(null);
  const [action, setAction] = useState("");
  const [resourceType, setResourceType] = useState("");
  const [result, setResult] = useState("");

  const load = () => {
    const qs = new URLSearchParams({ limit: "100" });
    if (action) qs.set("action", action);
    if (resourceType) qs.set("resource_type", resourceType);
    if (result) qs.set("result", result);
    apiFetch<AuditLogOut[]>(`/admin/audit-logs?${qs.toString()}`).then(setLogs).catch(() => setLogs([]));
  };

  useEffect(() => {
    if (user) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  if (loading) return <div className="mx-auto max-w-5xl px-6 py-16 text-slate-400">Loading…</div>;
  if (!user || !user.roles.some((r) => ["ADMIN", "SUPER_ADMIN"].includes(r))) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-slate-300">This area is for admins.</p>
        <Link href="/dashboard" className="btn-secondary mt-6 inline-flex">Back to dashboard</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-6 py-10">
      <h1 className="text-2xl font-bold text-white">Audit logs</h1>

      <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-4">
        <input className="input" placeholder="Action (e.g. certificate.revoke)" value={action} onChange={(e) => setAction(e.target.value)} />
        <input className="input" placeholder="Resource type" value={resourceType} onChange={(e) => setResourceType(e.target.value)} />
        <select className="input" value={result} onChange={(e) => setResult(e.target.value)}>
          <option value="">Any result</option>
          <option value="success">Success</option>
          <option value="failure">Failure</option>
        </select>
        <button onClick={load} className="btn-secondary">Filter</button>
      </div>

      <div className="card mt-6 overflow-x-auto p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-ink-800 text-left text-xs uppercase tracking-wide text-slate-500">
              <th className="px-4 py-3">When</th>
              <th className="px-4 py-3">Action</th>
              <th className="px-4 py-3">Resource</th>
              <th className="px-4 py-3">Actor</th>
              <th className="px-4 py-3">Result</th>
            </tr>
          </thead>
          <tbody>
            {(logs || []).map((l) => (
              <tr key={l.id} className="border-b border-ink-800 last:border-0">
                <td className="px-4 py-3 text-slate-400">{formatDateTime(l.created_at)}</td>
                <td className="px-4 py-3 text-slate-200">{l.action}</td>
                <td className="px-4 py-3 text-slate-400">{l.resource_type}{l.resource_id ? ` #${l.resource_id.slice(0, 8)}` : ""}</td>
                <td className="px-4 py-3 text-slate-500">{l.actor_id ? l.actor_id.slice(0, 8) : "system"}</td>
                <td className="px-4 py-3">
                  <span className={l.result === "success" ? "text-emerald-400" : "text-red-400"}>{l.result}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {logs !== null && logs.length === 0 && <p className="p-6 text-center text-sm text-slate-500">No matching audit log entries.</p>}
      </div>
    </div>
  );
}
