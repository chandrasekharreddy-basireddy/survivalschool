"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";

interface Preferences {
  course_updates: boolean;
  assessment_updates: boolean;
  achievement_updates: boolean;
  announcements: boolean;
  ai_notifications: boolean;
  email_enabled: boolean;
}

const LABELS: Record<keyof Preferences, string> = {
  course_updates: "Course updates",
  assessment_updates: "Quiz & exam results",
  achievement_updates: "Badges & achievements",
  announcements: "Platform announcements",
  ai_notifications: "AI tutor notifications",
  email_enabled: "Email notifications (in addition to in-app)",
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

  if (loading) return <div className="mx-auto max-w-2xl px-6 py-16 text-slate-400">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-slate-300">Sign in to view settings.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="text-2xl font-bold text-white">Settings</h1>

      <div className="card mt-8">
        <h2 className="font-semibold text-white">Account</h2>
        <dl className="mt-4 space-y-2 text-sm">
          <div className="flex justify-between"><dt className="text-slate-500">Name</dt><dd className="text-slate-200">{user.full_name}</dd></div>
          <div className="flex justify-between"><dt className="text-slate-500">Email</dt><dd className="text-slate-200">{user.email}</dd></div>
          <div className="flex justify-between"><dt className="text-slate-500">Email verified</dt><dd className="text-slate-200">{user.is_email_verified ? "Yes" : "No"}</dd></div>
        </dl>
      </div>

      <div className="card mt-6">
        <h2 className="font-semibold text-white">Notification preferences</h2>
        <div className="mt-4 space-y-3">
          {prefs === null ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : (
            (Object.keys(LABELS) as (keyof Preferences)[]).map((key) => (
              <label key={key} className="flex items-center justify-between text-sm text-slate-300">
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

      <div className="card mt-6 border-red-500/20">
        <h2 className="font-semibold text-white">Security</h2>
        <p className="mt-2 text-sm text-slate-400">Sign out of every device and session, including this one.</p>
        <button onClick={logoutAllSessions} className="btn-secondary mt-4">Sign out everywhere</button>
      </div>
    </div>
  );
}
