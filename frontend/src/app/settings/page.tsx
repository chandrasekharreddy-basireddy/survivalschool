"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";
import { getPushSupport, isSubscribedToPush, sendTestPush, subscribeToPush, unsubscribeFromPush } from "@/lib/push";
import { PageLoader } from "@/components/PageLoader";

interface Preferences {
  course_updates: boolean;
  assessment_updates: boolean;
  achievement_updates: boolean;
  social_notifications: boolean;
  announcements: boolean;
  ai_notifications: boolean;
  email_enabled: boolean;
  push_enabled: boolean;
}

const LABELS: Record<keyof Preferences, string> = {
  course_updates: "Timetable changes (room, time, cancellations)",
  assessment_updates: "Quiz & exam results",
  achievement_updates: "Badges & achievements",
  social_notifications: "Follow requests & connections",
  announcements: "Platform announcements",
  ai_notifications: "AI tutor notifications",
  email_enabled: "Email notifications (in addition to in-app)",
  push_enabled: "Browser push notifications (if subscribed below)",
};

export default function SettingsPage() {
  const { user, loading, logout } = useAuth();
  const toast = useToast();
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!user) return;
    apiFetch<Preferences>("/notifications/preferences").then(setPrefs).catch(() => {});
  }, [user]);

  const toggle = async (key: keyof Preferences) => {
    if (!prefs) return;
    const next = { ...prefs, [key]: !prefs[key] };
    setPrefs(next);
    setSaving(true);
    try {
      await apiFetch<Preferences>("/notifications/preferences", { method: "PATCH", body: JSON.stringify({ [key]: next[key] }) });
    } catch (err) {
      setPrefs(prefs);
      toast.show(err instanceof ApiError ? err.message : "Couldn't save that preference.", "error");
    } finally {
      setSaving(false);
    }
  };

  const logoutAllSessions = async () => {
    try {
      await apiFetch("/auth/logout-all", { method: "POST" });
      toast.show("Signed out of all devices.", "success");
      await logout();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't sign out of all devices.", "error");
    }
  };

  if (loading) return <div className="mx-auto max-w-2xl px-6 py-16 text-fg-muted"><PageLoader size="md" /></div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to view settings.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Settings</h1>

      <div className="card mt-8">
        <h2 className="font-semibold text-fg">Account</h2>
        <dl className="mt-4 space-y-2 text-sm">
          <div className="flex justify-between"><dt className="text-fg-subtle">Name</dt><dd className="text-fg">{user.full_name}</dd></div>
          <div className="flex justify-between"><dt className="text-fg-subtle">Email</dt><dd className="text-fg">{user.email}</dd></div>
          <div className="flex justify-between"><dt className="text-fg-subtle">Email verified</dt><dd className="text-fg">{user.is_email_verified ? "Yes" : "No"}</dd></div>
        </dl>
        <UsernameSection />
      </div>

      <div className="card mt-6">
        <h2 className="font-semibold text-fg">Notification preferences</h2>
        <div className="mt-4 space-y-3">
          {prefs === null ? (
            <p className="text-sm text-fg-subtle"><PageLoader size="sm" /></p>
          ) : (
            (Object.keys(LABELS) as (keyof Preferences)[]).map((key) => (
              <label key={key} className="flex items-center justify-between text-sm text-fg-muted">
                {LABELS[key]}
                <input
                  type="checkbox"
                  checked={prefs[key]}
                  onChange={() => toggle(key)}
                  disabled={saving}
                  className="h-4 w-4 accent-brand-500"
                />
              </label>
            ))
          )}
        </div>
      </div>

      <PushNotificationsSection />

      <TwoFactorSection />

      <div className="card mt-6 border-red-500/20">
        <h2 className="font-semibold text-fg">Security</h2>
        <SessionsSection />
        <p className="mt-6 text-sm text-fg-muted">Sign out of every device and session, including this one.</p>
        <button onClick={logoutAllSessions} className="btn-secondary mt-4">Sign out everywhere</button>
      </div>

      <DataPrivacySection />
    </div>
  );
}

function UsernameSection() {
  const toast = useToast();
  const [handle, setHandle] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<{ public_handle: string | null }>("/users/me/profile")
      .then((p) => { setHandle(p.public_handle); setInput(p.public_handle || ""); })
      .catch(() => {});
  }, []);

  const save = async () => {
    setError(null);
    const normalized = input.trim().toLowerCase();
    if (!/^[a-z0-9_]{3,30}$/.test(normalized)) {
      setError("3-30 characters: lowercase letters, numbers, and underscores only.");
      return;
    }
    setSaving(true);
    try {
      const updated = await apiFetch<{ public_handle: string | null }>("/users/me/profile", {
        method: "PATCH",
        body: JSON.stringify({ public_handle: normalized }),
      });
      setHandle(updated.public_handle);
      setInput(updated.public_handle || "");
      setEditing(false);
      toast.show("Username updated.", "success");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't update your username.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mt-4 border-t border-ink-700 pt-4">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-fg">Username</p>
          <p className="text-xs text-fg-subtle">Your unique @handle — how others find and invite you.</p>
        </div>
        {!editing && (
          <button onClick={() => setEditing(true)} className="btn-secondary shrink-0 !py-1.5 text-sm">
            {handle ? "Change" : "Set username"}
          </button>
        )}
      </div>
      {!editing ? (
        <p className="mt-2 text-sm text-fg-muted">{handle ? `@${handle}` : "Not set yet."}</p>
      ) : (
        <div className="mt-3 space-y-2">
          <input
            className="input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="e.g. jordan_23"
            maxLength={30}
          />
          {error && <p role="alert" className="text-xs font-medium text-danger">{error}</p>}
          <div className="flex gap-2">
            <button onClick={save} disabled={saving || !input.trim()} className="btn-primary !py-1.5 text-sm">
              {saving ? "Saving…" : "Save"}
            </button>
            <button
              onClick={() => { setEditing(false); setInput(handle || ""); setError(null); }}
              className="btn-secondary !py-1.5 text-sm"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

interface SessionInfo {
  id: string;
  device_label: string | null;
  ip_address: string | null;
  created_at: string;
  last_seen_at: string;
  is_current: boolean;
}

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60_000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

function SessionsSection() {
  const toast = useToast();
  const [sessions, setSessions] = useState<SessionInfo[] | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const load = () => {
    apiFetch<SessionInfo[]>("/auth/sessions").then(setSessions).catch(() => setSessions([]));
  };

  useEffect(load, []);

  const revoke = async (session: SessionInfo) => {
    if (!window.confirm(`Sign out "${session.device_label ?? "this device"}"? It'll need to log in again.`)) return;
    setRevokingId(session.id);
    try {
      await apiFetch(`/auth/sessions/${session.id}`, { method: "DELETE" });
      setSessions((prev) => prev && prev.filter((s) => s.id !== session.id));
      toast.show("Device signed out.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't sign out that device.", "error");
    } finally {
      setRevokingId(null);
    }
  };

  return (
    <div>
      <h3 className="text-sm font-medium text-fg">Your devices</h3>
      <p className="mt-1 text-xs text-fg-subtle">Everywhere you&apos;re currently signed in. Don&apos;t recognize one? Sign it out.</p>
      <div className="mt-3 space-y-2">
        {sessions === null && <p className="text-sm text-fg-subtle"><PageLoader size="sm" /></p>}
        {sessions !== null && sessions.length === 0 && <p className="text-sm text-fg-subtle">No active sessions found.</p>}
        {sessions?.map((s) => (
          <div key={s.id} className="flex items-center justify-between gap-3 rounded-lg border border-ink-700 px-3 py-2 text-sm">
            <div className="min-w-0">
              <p className="truncate text-fg">
                {s.device_label ?? "Unknown device"}
                {s.is_current && <span className="ml-2 rounded-full border border-emerald-500/40 px-2 py-0.5 text-xs text-emerald-600 dark:text-emerald-400">This device</span>}
              </p>
              <p className="truncate text-xs text-fg-subtle">
                {s.ip_address ?? "Unknown IP"} · active {relativeTime(s.last_seen_at)}
              </p>
            </div>
            {!s.is_current && (
              <button
                onClick={() => revoke(s)}
                disabled={revokingId === s.id}
                className="btn-secondary shrink-0 !py-1 !text-xs disabled:opacity-60"
              >
                {revokingId === s.id ? "Signing out…" : "Sign out"}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function PushNotificationsSection() {
  const toast = useToast();
  const [support, setSupport] = useState<{ supported: boolean; permission: NotificationPermission | "unsupported" } | null>(null);
  const [subscribed, setSubscribed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    const s = getPushSupport();
    setSupport(s);
    if (s.supported) {
      isSubscribedToPush().then(setSubscribed);
    }
  }, []);

  const enable = async () => {
    setBusy(true);
    try {
      await subscribeToPush();
      setSubscribed(true);
      toast.show("Push notifications enabled on this device.", "success");
    } catch (err) {
      toast.show(err instanceof Error ? err.message : "Couldn't enable push notifications.", "error");
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    setBusy(true);
    try {
      await unsubscribeFromPush();
      setSubscribed(false);
      toast.show("Push notifications disabled on this device.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't disable push notifications.", "error");
    } finally {
      setBusy(false);
    }
  };

  const test = async () => {
    setTesting(true);
    try {
      const sent = await sendTestPush();
      toast.show(sent > 0 ? "Test notification sent — check your device." : "No active subscription to send to.", sent > 0 ? "success" : "error");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't send a test notification.", "error");
    } finally {
      setTesting(false);
    }
  };

  if (!support) return null;

  return (
    <div className="card mt-6">
      <h2 className="font-semibold text-fg">Push notifications</h2>
      <p className="mt-2 text-sm text-fg-muted">
        Get real browser notifications for exam reminders, contest results, and replies — even when this tab isn&apos;t open.
      </p>

      {!support.supported ? (
        <p className="mt-3 text-sm text-fg-subtle">Not supported in this browser.</p>
      ) : support.permission === "denied" ? (
        <p className="mt-3 text-sm text-fg-subtle">
          Notifications are blocked for this site in your browser settings — enable them there to use this.
        </p>
      ) : subscribed ? (
        <div className="mt-3 flex items-center gap-2">
          <button onClick={test} disabled={testing} className="btn-secondary !py-1.5 text-sm">
            {testing ? "Sending…" : "Send test notification"}
          </button>
          <button onClick={disable} disabled={busy} className="btn-secondary !py-1.5 text-sm">
            {busy ? "Disabling…" : "Turn off on this device"}
          </button>
        </div>
      ) : (
        <button onClick={enable} disabled={busy} className="btn-primary mt-3">
          {busy ? "Enabling…" : "Enable on this device"}
        </button>
      )}
    </div>
  );
}

function DataPrivacySection() {
  const { logout } = useAuth();
  const toast = useToast();
  const [exporting, setExporting] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [deletePassword, setDeletePassword] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deleting, setDeleting] = useState(false);

  const exportData = async () => {
    setExporting(true);
    try {
      const data = await apiFetch<Record<string, unknown>>("/users/me/export");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `survivalschool-data-export-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.show("Your data export has downloaded.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't generate your export.", "error");
    } finally {
      setExporting(false);
    }
  };

  const deleteAccount = async () => {
    if (deleteConfirm !== "DELETE" || !deletePassword) return;
    setDeleting(true);
    try {
      await apiFetch("/users/me/delete-account", {
        method: "POST",
        body: JSON.stringify({ password: deletePassword, confirm: deleteConfirm }),
      });
      toast.show("Your account has been deleted.", "success");
      await logout();
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't delete your account.", "error");
      setDeleting(false);
    }
  };

  return (
    <div className="card mt-6">
      <h2 className="font-semibold text-fg">Data &amp; privacy</h2>
      <p className="mt-2 text-sm text-fg-muted">
        Download everything tied to your account, or permanently delete it.
      </p>

      <div className="mt-4 flex items-center justify-between border-b border-ink-700 pb-4">
        <div>
          <p className="text-sm font-medium text-fg">Export my data</p>
          <p className="text-xs text-fg-subtle">A JSON file with your profile, contest and practice history, certificates, points, and more.</p>
        </div>
        <button onClick={exportData} disabled={exporting} className="btn-secondary shrink-0">
          {exporting ? "Preparing…" : "Download"}
        </button>
      </div>

      <div className="mt-4">
        <p className="text-sm font-medium text-red-700 dark:text-red-400">Delete my account</p>
        <p className="text-xs text-fg-subtle">
          Permanently erases your profile, progress, attempts, and personal history. Content you posted that other
          people rely on (discussion replies, chat messages) stays visible but is no longer attributed to you.
          This cannot be undone.
        </p>
        {showDelete ? (
          <div className="mt-3 space-y-3">
            <div>
              <label className="label">Confirm your password</label>
              <input type="password" className="input" value={deletePassword} onChange={(e) => setDeletePassword(e.target.value)} />
            </div>
            <div>
              <label className="label">Type DELETE to confirm</label>
              <input className="input" value={deleteConfirm} onChange={(e) => setDeleteConfirm(e.target.value)} placeholder="DELETE" />
            </div>
            <div className="flex gap-2">
              <button
                onClick={deleteAccount}
                disabled={deleting || !deletePassword || deleteConfirm !== "DELETE"}
                className="btn-secondary text-red-700 dark:text-red-400"
              >
                {deleting ? "Deleting…" : "Permanently delete my account"}
              </button>
              <button onClick={() => { setShowDelete(false); setDeletePassword(""); setDeleteConfirm(""); }} className="btn-secondary">
                Cancel
              </button>
            </div>
          </div>
        ) : (
          <button onClick={() => setShowDelete(true)} className="btn-secondary mt-3 !py-1.5 text-sm text-red-700 dark:text-red-400">
            Delete my account
          </button>
        )}
      </div>
    </div>
  );
}

interface TwoFactorSetupOut { secret: string; otpauth_url: string; qr_code_data_uri: string }

function TwoFactorSection() {
  const { user, refreshUser } = useAuth();
  const toast = useToast();
  const [setup, setSetup] = useState<TwoFactorSetupOut | null>(null);
  const [confirmCode, setConfirmCode] = useState("");
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [disablePassword, setDisablePassword] = useState("");
  const [showDisable, setShowDisable] = useState(false);
  const [busy, setBusy] = useState(false);

  const startSetup = async () => {
    setBusy(true);
    try {
      const res = await apiFetch<TwoFactorSetupOut>("/auth/2fa/setup", { method: "POST" });
      setSetup(res);
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't start 2FA setup.", "error");
    } finally {
      setBusy(false);
    }
  };

  const confirmSetup = async () => {
    setBusy(true);
    try {
      const res = await apiFetch<{ backup_codes: string[] }>("/auth/2fa/confirm", {
        method: "POST", body: JSON.stringify({ code: confirmCode.trim() }),
      });
      setBackupCodes(res.backup_codes);
      setSetup(null);
      setConfirmCode("");
      await refreshUser();
      toast.show("Two-factor authentication enabled.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Incorrect code — try again.", "error");
    } finally {
      setBusy(false);
    }
  };

  const disable = async () => {
    if (!disablePassword) return;
    setBusy(true);
    try {
      await apiFetch("/auth/2fa/disable", { method: "POST", body: JSON.stringify({ password: disablePassword }) });
      setShowDisable(false);
      setDisablePassword("");
      await refreshUser();
      toast.show("Two-factor authentication disabled.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Incorrect password.", "error");
    } finally {
      setBusy(false);
    }
  };

  if (!user) return null;

  return (
    <div className="card mt-6">
      <h2 className="font-semibold text-fg">Two-factor authentication</h2>
      <p className="mt-2 text-sm text-fg-muted">
        Adds a 6-digit code from an authenticator app (Google Authenticator, Authy, 1Password, etc.) on top of your password.
      </p>

      {backupCodes ? (
        <div className="mt-4 rounded-lg border border-amber-500/40 bg-amber-500/5 p-4">
          <p className="text-sm font-medium text-fg">Save these backup codes now — they won&apos;t be shown again.</p>
          <p className="mt-1 text-xs text-fg-subtle">Each one can be used once if you lose access to your authenticator app.</p>
          <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-sm text-fg">
            {backupCodes.map((c) => <span key={c} className="rounded bg-ink-900 px-2 py-1">{c}</span>)}
          </div>
          <button onClick={() => setBackupCodes(null)} className="btn-secondary mt-4 !py-1.5 text-sm">I&apos;ve saved these</button>
        </div>
      ) : setup ? (
        <div className="mt-4 space-y-4">
          <div className="flex flex-col items-center gap-3 rounded-lg border border-ink-700 p-4">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={setup.qr_code_data_uri} alt="2FA QR code" className="h-40 w-40 rounded bg-white p-2" />
            <p className="text-xs text-fg-subtle">Can&apos;t scan? Enter this key manually:</p>
            <code className="rounded bg-ink-900 px-2 py-1 text-xs text-fg">{setup.secret}</code>
          </div>
          <div>
            <label className="label">Enter the 6-digit code from your app</label>
            <input
              className="input font-mono tracking-widest" placeholder="123456" maxLength={8}
              value={confirmCode} onChange={(e) => setConfirmCode(e.target.value)}
            />
          </div>
          <div className="flex gap-2">
            <button onClick={confirmSetup} disabled={busy || !confirmCode.trim()} className="btn-primary">
              {busy ? "Verifying…" : "Enable 2FA"}
            </button>
            <button onClick={() => setSetup(null)} className="btn-secondary">Cancel</button>
          </div>
        </div>
      ) : user.totp_enabled ? (
        <div className="mt-4">
          <p className="text-sm font-medium text-emerald-700 dark:text-emerald-400">2FA is enabled on your account.</p>
          {showDisable ? (
            <div className="mt-3 space-y-3">
              <div>
                <label className="label">Confirm your password to disable 2FA</label>
                <input type="password" className="input" value={disablePassword} onChange={(e) => setDisablePassword(e.target.value)} />
              </div>
              <div className="flex gap-2">
                <button onClick={disable} disabled={busy || !disablePassword} className="btn-secondary text-red-700 dark:text-red-400">
                  {busy ? "Disabling…" : "Confirm disable"}
                </button>
                <button onClick={() => { setShowDisable(false); setDisablePassword(""); }} className="btn-secondary">Cancel</button>
              </div>
            </div>
          ) : (
            <button onClick={() => setShowDisable(true)} className="btn-secondary mt-3 !py-1.5 text-sm text-red-700 dark:text-red-400">Disable 2FA</button>
          )}
        </div>
      ) : (
        <button onClick={startSetup} disabled={busy} className="btn-primary mt-4">
          {busy ? "Starting…" : "Set up two-factor authentication"}
        </button>
      )}
    </div>
  );
}
