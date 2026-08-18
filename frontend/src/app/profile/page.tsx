"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
const MAX_AVATAR_MB = 25;
const AVATAR_ACCEPT = "image/png,image/jpeg,image/gif,image/webp";

interface Profile {
  bio: string | null;
  avatar_url: string | null;
  timezone: string;
  locale: string;
}

interface FileOut {
  id: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  visibility: string;
  scan_status: string;
  url: string;
}

interface GamificationStats {
  total_points: number;
  current_streak_days: number;
  longest_streak_days: number;
  badges: { code: string; name: string; icon: string; awarded_at: string }[];
}

interface CertificateOut {
  certificate_number: string;
  course_title: string;
}

export default function ProfilePage() {
  const { user, loading } = useAuth();
  const toast = useToast();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [stats, setStats] = useState<GamificationStats | null>(null);
  const [certs, setCerts] = useState<CertificateOut[] | null>(null);
  const [bio, setBio] = useState("");
  const [saving, setSaving] = useState(false);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const avatarInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!user) return;
    apiFetch<Profile>("/users/me/profile").then((p) => { setProfile(p); setBio(p.bio || ""); }).catch(() => {});
    apiFetch<GamificationStats>("/gamification/me").then(setStats).catch(() => {});
    apiFetch<CertificateOut[]>("/certificates/me").then(setCerts).catch(() => setCerts([]));
  }, [user]);

  const onAvatarSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const maxBytes = MAX_AVATAR_MB * 1024 * 1024;
    if (file.size > maxBytes) {
      toast.show(`That image is too large. The limit is ${MAX_AVATAR_MB}MB.`, "error");
      return;
    }
    setUploadingAvatar(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const uploaded = await apiFetch<FileOut>("/files?visibility=public", {
        method: "POST",
        body: formData,
      });
      const avatarUrl = `${API_BASE}${uploaded.url}`;
      const updated = await apiFetch<Profile>("/users/me/profile", {
        method: "PATCH",
        body: JSON.stringify({ avatar_url: avatarUrl }),
      });
      setProfile(updated);
      toast.show("Avatar updated.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't upload your avatar.", "error");
    } finally {
      setUploadingAvatar(false);
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      const updated = await apiFetch<Profile>("/users/me/profile", { method: "PATCH", body: JSON.stringify({ bio }) });
      setProfile(updated);
      toast.show("Profile updated.", "success");
    } catch (err) {
      toast.show(err instanceof ApiError ? err.message : "Couldn't save your profile.", "error");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="mx-auto max-w-3xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">Sign in to view your profile.</p>
        <Link href="/login" className="btn-primary mt-6 inline-flex">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={() => avatarInputRef.current?.click()}
          disabled={uploadingAvatar}
          className="group relative flex h-16 w-16 shrink-0 items-center justify-center rounded-full disabled:cursor-wait"
          title="Change avatar"
        >
          {profile?.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element -- user-uploaded avatar from arbitrary storage URL, not a static/known-dimension asset next/image needs
            <img
              src={profile.avatar_url}
              alt={`${user.full_name}'s avatar`}
              className="h-16 w-16 rounded-full object-cover"
            />
          ) : (
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-brand-600 text-xl font-semibold text-white">
              {user.full_name.slice(0, 1).toUpperCase()}
            </div>
          )}
          <div className="absolute inset-0 flex items-center justify-center rounded-full bg-black/50 text-[10px] font-medium text-white opacity-0 transition group-hover:opacity-100">
            {uploadingAvatar ? "Uploading…" : "Change"}
          </div>
        </button>
        <input
          ref={avatarInputRef}
          type="file"
          accept={AVATAR_ACCEPT}
          onChange={onAvatarSelected}
          disabled={uploadingAvatar}
          className="hidden"
        />
        <div>
          <h1 className="text-2xl font-bold text-fg">{user.full_name}</h1>
          <p className="text-sm text-fg-subtle">{user.email}</p>
          <div className="mt-1 flex gap-1.5">
            {user.roles.map((r) => (
              <span key={r} className="rounded bg-ink-800 px-2 py-0.5 text-[11px] uppercase tracking-wide text-fg-muted">{r}</span>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-8 grid gap-6 sm:grid-cols-3">
        <div className="card text-center">
          <p className="text-2xl font-bold text-brand-600 dark:text-brand-400">{stats?.total_points ?? "—"}</p>
          <p className="text-xs text-fg-subtle">points</p>
        </div>
        <div className="card text-center">
          <p className="text-2xl font-bold text-brand-600 dark:text-brand-400">{stats?.current_streak_days ?? "—"}</p>
          <p className="text-xs text-fg-subtle">day streak</p>
        </div>
        <div className="card text-center">
          <p className="text-2xl font-bold text-brand-600 dark:text-brand-400">{certs?.length ?? "—"}</p>
          <p className="text-xs text-fg-subtle">certificates</p>
        </div>
      </div>

      {stats && stats.badges.length > 0 && (
        <div className="card mt-6">
          <h2 className="font-semibold text-fg">Badges</h2>
          <div className="mt-4 flex flex-wrap gap-2">
            {stats.badges.map((b) => (
              <span key={b.code} className="rounded-full bg-brand-500/10 px-3 py-1 text-xs text-brand-300">{b.name}</span>
            ))}
          </div>
        </div>
      )}

      <div className="card mt-6">
        <h2 className="font-semibold text-fg">About</h2>
        <textarea
          className="input mt-3 min-h-[100px]"
          value={bio}
          onChange={(e) => setBio(e.target.value)}
          placeholder="Tell other students a bit about yourself…"
          maxLength={500}
        />
        <button onClick={save} disabled={saving || !profile} className="btn-primary mt-3">
          {saving ? "Saving…" : "Save"}
        </button>
      </div>

      {certs && certs.length > 0 && (
        <div className="card mt-6">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-fg">Certificates</h2>
            <Link href="/certificates/me" className="text-sm text-brand-600 dark:text-brand-400 hover:underline">View all</Link>
          </div>
          <ul className="mt-3 space-y-2">
            {certs.slice(0, 3).map((c) => (
              <li key={c.certificate_number} className="text-sm text-fg-muted">{c.course_title}</li>
            ))}
          </ul>
        </div>
      )}

      <Link href="/settings" className="mt-6 inline-block text-sm text-fg-muted hover:text-fg">Account settings &rarr;</Link>
    </div>
  );
}
