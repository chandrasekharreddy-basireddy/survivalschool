"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";
import { useToast } from "@/lib/toast";

function slugify(title: string) {
  return title.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
}

export default function CreateCoursePage() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const toast = useToast();

  const [title, setTitle] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [description, setDescription] = useState("");
  const [difficulty, setDifficulty] = useState("beginner");
  const [estimatedHours, setEstimatedHours] = useState(1);
  const [specialization, setSpecialization] = useState("");
  const [skillsInput, setSkillsInput] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (loading) return <div className="mx-auto max-w-2xl px-6 py-16 text-fg-muted">Loading…</div>;
  if (!user || !user.roles.some((r) => ["INSTRUCTOR", "ADMIN", "SUPER_ADMIN"].includes(r))) {
    return (
      <div className="mx-auto max-w-md px-6 py-24 text-center">
        <p className="text-fg-muted">This area is for instructors.</p>
        <Link href="/dashboard" className="btn-secondary mt-6 inline-flex">Back to dashboard</Link>
      </div>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const course = await apiFetch<{ id: string }>("/courses", {
        method: "POST",
        body: JSON.stringify({
          title, slug: slug || slugify(title), description, difficulty,
          estimated_hours: estimatedHours, specialization: specialization || null,
          skills: skillsInput.split(",").map((s) => s.trim()).filter(Boolean),
        }),
      });
      toast.show("Course created — now add sections and lessons.", "success");
      router.push(`/instructor/courses/${course.id}/edit`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create the course.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl px-6 py-10">
      <h1 className="text-2xl font-bold text-fg">Create a course</h1>
      <form onSubmit={submit} className="card mt-8 space-y-5">
        <div>
          <label className="label">Title</label>
          <input
            className="input"
            value={title}
            onChange={(e) => { setTitle(e.target.value); if (!slugTouched) setSlug(slugify(e.target.value)); }}
            required
            minLength={3}
          />
        </div>
        <div>
          <label className="label">URL slug</label>
          <input className="input" value={slug} onChange={(e) => { setSlug(slugify(e.target.value)); setSlugTouched(true); }} required minLength={3} pattern="[a-z0-9-]+" />
        </div>
        <div>
          <label className="label">Description</label>
          <textarea className="input min-h-[100px]" value={description} onChange={(e) => setDescription(e.target.value)} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label">Difficulty</label>
            <select className="input" value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
              <option value="beginner">Beginner</option>
              <option value="intermediate">Intermediate</option>
              <option value="advanced">Advanced</option>
            </select>
          </div>
          <div>
            <label className="label">Estimated hours</label>
            <input type="number" min={0} className="input" value={estimatedHours} onChange={(e) => setEstimatedHours(Number(e.target.value))} />
          </div>
        </div>
        <div>
          <label className="label">Specialization / track (optional)</label>
          <input className="input" value={specialization} onChange={(e) => setSpecialization(e.target.value)} placeholder="e.g. Backend Engineering" />
        </div>
        <div>
          <label className="label">Skills taught (comma-separated)</label>
          <input className="input" value={skillsInput} onChange={(e) => setSkillsInput(e.target.value)} placeholder="Python, SQL, System Design" />
          <p className="mt-1 text-xs text-fg-subtle">These appear on certificates students earn for this course.</p>
        </div>

        {error && <p className="text-sm text-red-400">{error}</p>}

        <button type="submit" disabled={saving} className="btn-primary w-full">
          {saving ? "Creating…" : "Create course"}
        </button>
      </form>
    </div>
  );
}
