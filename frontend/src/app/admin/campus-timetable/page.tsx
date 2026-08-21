"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { PageLoader } from "@/components/PageLoader";

interface SourceOut {
  mode: string;
  sheet_csv_url: string | null;
  poll_interval_minutes: number;
  last_synced_at: string | null;
  last_sync_status: string | null;
  last_sync_error: string | null;
  last_sync_row_count: number;
}

interface SyncResultOut {
  total_rows: number;
  error_rows: { row_number: number; error: string }[];
  created: number;
  updated: number;
  cancelled: number;
  unchanged: number;
  change_count: number;
}

export default function CampusTimetableAdminPage() {
  const { user, loading } = useAuth();
  const toast = useToast();
  const [source, setSource] = useState<SourceOut | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [lastResult, setLastResult] = useState<SyncResultOut | null>(null);

  const [csvUrl, setCsvUrl] = useState("");
  const [pollMinutes, setPollMinutes] = useState(15);
  const [savingLiveSync, setSavingLiveSync] = useState(false);
  const [dragging, setDragging] = useState(false);

  const load = () => {
    apiFetch<SourceOut>("/timetable/campus/source").then((s) => {
      setSource(s);
      if (s.sheet_csv_url) setCsvUrl(s.sheet_csv_url);
      setPollMinutes(s.poll_interval_minutes);
    }).catch(() => setSource(null));
  };

  useEffect(() => {
    if (user) load();
  }, [user]);

  const upload = async () => {
    if (!uploadFile) return;
    setUploading(true);
    try {
      const body = new FormData();
      body.append("file", uploadFile);
      const result = await apiFetch<SyncResultOut>("/timetable/campus/upload", { method: "POST", body });
      setLastResult(result);
      toast.show(
        result.error_rows.length
          ? `${result.error_rows.length} row(s) failed — nothing was imported.`
          : `Imported: ${result.created} new, ${result.updated} updated, ${result.cancelled} cancelled.`,
        result.error_rows.length ? "error" : "success"
      );
      setUploadFile(null);
      load();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Upload failed.", "error");
    } finally {
      setUploading(false);
    }
  };

  const saveLiveSync = async () => {
    setSavingLiveSync(true);
    try {
      const s = await apiFetch<SourceOut>("/timetable/campus/live-sync", {
        method: "PUT",
        body: JSON.stringify({ csv_url: csvUrl.trim(), poll_interval_minutes: pollMinutes }),
      });
      setSource(s);
      toast.show("Live sync enabled — polling on the configured interval from now on.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't enable live sync.", "error");
    } finally {
      setSavingLiveSync(false);
    }
  };

  const disableLiveSync = async () => {
    try {
      const s = await apiFetch<SourceOut>("/timetable/campus/live-sync", { method: "DELETE" });
      setSource(s);
      setCsvUrl("");
      toast.show("Live sync disabled.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't disable live sync.", "error");
    }
  };

  if (loading) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted"><PageLoader size="md" /></div>;
  if (!user || !user.roles.some((r) => ["ADMIN", "SUPER_ADMIN"].includes(r))) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">This area is for admins.</p>
        <Link href="/dashboard" className="btn-secondary mt-6 inline-flex">Back to dashboard</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-fg">Campus timetable</h1>
        <Link href="/admin" className="text-sm text-brand-600 dark:text-brand-400 hover:underline">Admin console &rarr;</Link>
      </div>
      <p className="mt-1 text-sm text-fg-muted">
        The university-wide class schedule — separate from each instructor&apos;s own course timetable. Students pick
        their section from a real dropdown on the Timetable page (built from whatever&apos;s actually in the file you
        upload here), or upload their own personal schedule instead if they&apos;d rather not wait for yours.
      </p>

      {source && (
        <div className="card mt-6">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold text-fg">Current source</p>
            <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${source.mode === "live_sync" ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" : "bg-ink-800 text-fg-muted"}`}>
              {source.mode === "live_sync" ? "Live sync" : "Manual upload"}
            </span>
          </div>
          <div className="mt-2 text-xs text-fg-muted">
            {source.last_synced_at ? (
              <p>
                Last synced {new Date(source.last_synced_at).toLocaleString()} —{" "}
                <span className={source.last_sync_status === "ok" ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400"}>
                  {source.last_sync_status === "ok" ? `${source.last_sync_row_count} rows` : source.last_sync_error || "error"}
                </span>
              </p>
            ) : (
              <p>Never synced yet.</p>
            )}
          </div>
        </div>
      )}

      <div className="card mt-6">
        <p className="text-sm font-semibold text-fg">Upload a file</p>
        <p className="mt-1 text-xs text-fg-muted">
          CSV or XLSX with columns like School, Year, Section, LabGroup, Course, CourseId, Date, StartTime, EndTime,
          Room, Teacher, Elective (extra/missing optional columns are fine). Re-uploading diffs against what&apos;s
          already stored — changed rows update, dropped rows are marked cancelled instead of deleted.
        </p>
        <label
          htmlFor="campus-timetable-file"
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const dropped = e.dataTransfer.files?.[0];
            if (dropped) setUploadFile(dropped);
          }}
          className={`mt-3 flex cursor-pointer flex-col items-center justify-center gap-1 rounded-lg border-2 border-dashed px-4 py-8 text-center transition ${
            dragging ? "border-brand-500 bg-brand-500/5" : "border-ink-700 hover:border-ink-600"
          }`}
        >
          <input
            id="campus-timetable-file"
            type="file"
            accept=".csv,.xlsx"
            className="sr-only"
            onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
          />
          <p className="text-sm font-medium text-fg">
            {uploadFile ? uploadFile.name : "Drag & drop a CSV or XLSX file here"}
          </p>
          <p className="text-xs text-fg-subtle">{uploadFile ? "Click to choose a different file" : "or click to browse"}</p>
        </label>
        <div className="mt-3 flex items-center gap-2">
          <button onClick={upload} disabled={uploading || !uploadFile} className="btn-primary !px-3 !py-1.5 text-sm">
            {uploading ? "Uploading…" : "Upload"}
          </button>
          {uploadFile && (
            <button onClick={() => setUploadFile(null)} className="btn-secondary !px-3 !py-1.5 text-sm">Clear</button>
          )}
        </div>
        {lastResult && lastResult.error_rows.length > 0 && (
          <div className="mt-3 rounded border border-red-500/30 bg-red-500/5 p-2 text-[11px] text-red-800 dark:text-red-300">
            <p className="font-medium">Nothing was imported — fix these rows and re-upload:</p>
            <ul className="mt-1 space-y-0.5">
              {lastResult.error_rows.map((r, i) => <li key={i}>Row {r.row_number}: {r.error}</li>)}
            </ul>
          </div>
        )}
      </div>

      <div className="card mt-6">
        <p className="text-sm font-semibold text-fg">Live sync from a published sheet</p>
        <p className="mt-1 text-xs text-fg-muted">
          Point this at a Google Sheets &quot;Publish to web&quot; CSV export link (File → Share → Publish to web →
          CSV). The server polls it on the interval below and applies the same diff logic as a manual upload — edit
          the sheet and changes show up here automatically.
        </p>
        <div className="mt-3 space-y-2">
          <input
            className="input"
            placeholder="https://docs.google.com/spreadsheets/d/.../pub?output=csv"
            value={csvUrl}
            onChange={(e) => setCsvUrl(e.target.value)}
          />
          <div className="flex items-center gap-2">
            <label className="text-xs text-fg-muted">Poll every</label>
            <input
              type="number"
              min={5}
              max={1440}
              className="input !w-20 !py-1"
              value={pollMinutes}
              onChange={(e) => setPollMinutes(Number(e.target.value))}
            />
            <span className="text-xs text-fg-muted">minutes</span>
          </div>
          <div className="flex gap-2">
            <button onClick={saveLiveSync} disabled={savingLiveSync || !csvUrl.trim()} className="btn-primary !px-3 !py-1.5 text-sm">
              {savingLiveSync ? "Syncing…" : source?.mode === "live_sync" ? "Update & re-sync" : "Enable live sync"}
            </button>
            {source?.mode === "live_sync" && (
              <button onClick={disableLiveSync} className="btn-secondary !px-3 !py-1.5 text-sm">Disable</button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
