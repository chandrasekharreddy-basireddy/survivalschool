"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { apiFetch, ApiError } from "@/lib/api";

interface Battle { id: string }

/** The landing target for a shared room code or a scanned QR — auto-joins
 * the battle and drops the player straight into the lobby, matching the
 * "custom match, join by room id" flow the code/QR was built for. */
export default function JoinBattlePage() {
  const params = useParams<{ code: string }>();
  const router = useRouter();
  const { user, loading } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const attempted = useRef(false);

  useEffect(() => {
    if (loading) return;
    if (!user) {
      const next = encodeURIComponent(`/elimination/join/${params.code}`);
      router.replace(`/login?next=${next}`);
      return;
    }
    if (attempted.current) return;
    attempted.current = true;
    apiFetch<Battle>("/elimination/battles/join", { method: "POST", body: JSON.stringify({ code: params.code }) })
      .then((battle) => router.replace(`/elimination/${battle.id}`))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Couldn't join that battle."));
  }, [user, loading, params.code, router]);

  return (
    <div className="mx-auto max-w-md px-6 py-24 text-center">
      {error ? (
        <>
          <p className="text-fg">{error}</p>
          <Link href="/elimination" className="btn-primary mt-6 inline-flex">All battles</Link>
        </>
      ) : (
        <p className="text-fg-muted">Joining battle&hellip;</p>
      )}
    </div>
  );
}
